"""M6: aggregation of M4's recommendation log (added for this module),
the honest no-data case, and the stock_signal heuristic. Every test gets
isolated SQLite files for both the recommendation log and the outcome
store (M9's evidence source), so runs don't leak into the real dev
databases or into each other.
"""
import pytest

from app.schemas.outcome_log import OutcomeLogInput
from app.services import outcome_log, outcome_store, recommendation_log, retailer


@pytest.fixture
def isolated_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(recommendation_log, "DB_PATH", tmp_path / "recommendation_log.sqlite3")
    monkeypatch.setattr(outcome_store, "DB_PATH", tmp_path / "outcome_log_cache.sqlite3")
    return recommendation_log


def _log_rec(district, product, confidence=0.7, n=1):
    for _ in range(n):
        recommendation_log.log_recommendation(district, product, confidence)


def _log_outcome(product, district, yield_result=30.0, farmer="f-1"):
    outcome_log.log_outcome(
        OutcomeLogInput(
            farmer_id=farmer,
            product_used=product,
            batch_number="TRV-2026-00417",
            application_date="2026-03-14",
            observed_outcome="improvement",
            yield_result=yield_result,
            district=district,
        )
    )


# --- aggregation against synthetic recommendation history ------------------

def test_aggregation_counts_and_averages_confidence_per_product(isolated_logs):
    recommendation_log.log_recommendation("Ludhiana", "Product A", 0.6)
    recommendation_log.log_recommendation("Ludhiana", "Product A", 0.8)
    recommendation_log.log_recommendation("Ludhiana", "Product B", 0.9)

    console = retailer.get_district_console("Ludhiana")
    by_name = {r.product_name: r for r in console.recent_recommendations}

    assert by_name["Product A"].count == 2
    assert by_name["Product A"].avg_confidence == pytest.approx(0.7)
    assert by_name["Product B"].count == 1
    assert by_name["Product B"].avg_confidence == pytest.approx(0.9)


def test_aggregation_sorted_by_count_descending(isolated_logs):
    _log_rec("Ludhiana", "Rare Product", n=1)
    _log_rec("Ludhiana", "Common Product", n=5)
    _log_rec("Ludhiana", "Medium Product", n=3)

    console = retailer.get_district_console("Ludhiana")
    names_in_order = [r.product_name for r in console.recent_recommendations]
    assert names_in_order == ["Common Product", "Medium Product", "Rare Product"]


def test_aggregation_only_includes_the_requested_district(isolated_logs):
    _log_rec("Ludhiana", "Product A", n=3)
    _log_rec("Amritsar", "Product A", n=7)

    console = retailer.get_district_console("Ludhiana")
    assert len(console.recent_recommendations) == 1
    assert console.recent_recommendations[0].count == 3


# --- honest no-data case -----------------------------------------------------

def test_district_with_no_activity_returns_honest_empty_response(isolated_logs):
    console = retailer.get_district_console("Nowhere Logged")
    assert console.district == "Nowhere Logged"
    assert console.recent_recommendations == []
    assert console.stock_signal == []
    assert console.generated_at  # still a real timestamp, not omitted


def test_product_with_no_logged_outcomes_says_so_honestly(isolated_logs):
    _log_rec("Ludhiana", "Product A", n=1)
    console = retailer.get_district_console("Ludhiana")
    summary = console.recent_recommendations[0]
    assert summary.outcomes_logged == 0
    assert "no outcomes logged yet" in summary.avg_outcome_summary


def test_product_with_real_logged_outcomes_reports_them(isolated_logs):
    product = "Trichoderma viride bio-fungicide"
    _log_rec("Ludhiana", product, n=1)
    _log_outcome(product, "Ludhiana", yield_result=30.0, farmer="f-1")
    _log_outcome(product, "Ludhiana", yield_result=5.0, farmer="f-2")

    console = retailer.get_district_console("Ludhiana")
    summary = console.recent_recommendations[0]
    assert summary.outcomes_logged == 2
    assert "1 of 2" in summary.avg_outcome_summary


# --- stock_signal: plain frequency aggregation, not a forecast -------------

def test_stock_signal_empty_for_no_activity(isolated_logs):
    console = retailer.get_district_console("Nowhere Logged")
    assert console.stock_signal == []


def test_stock_signal_single_product_is_high(isolated_logs):
    _log_rec("Ludhiana", "Only Product", n=3)
    console = retailer.get_district_console("Ludhiana")
    assert console.stock_signal[0].demand_level == "high"


def test_stock_signal_uniform_distribution_is_all_high(isolated_logs):
    _log_rec("Ludhiana", "Product A", n=4)
    _log_rec("Ludhiana", "Product B", n=4)
    console = retailer.get_district_console("Ludhiana")
    assert all(s.demand_level == "high" for s in console.stock_signal)


def test_stock_signal_clear_leader_vs_long_tail(isolated_logs):
    _log_rec("Ludhiana", "Leader", n=10)
    _log_rec("Ludhiana", "Middling", n=5)
    _log_rec("Ludhiana", "Rare", n=1)

    console = retailer.get_district_console("Ludhiana")
    by_name = {s.product_name: s.demand_level for s in console.stock_signal}
    assert by_name["Leader"] == "high"
    assert by_name["Middling"] == "medium"
    assert by_name["Rare"] == "low"


def test_stock_signal_ratios_match_the_documented_thresholds():
    from app.schemas.retailer import RecentRecommendation

    def _fake(count):
        return RecentRecommendation(
            product_name=f"p-{count}", count=count, avg_confidence=0.5, outcomes_logged=0, avg_outcome_summary=""
        )

    # max=10: ratios 1.0, 0.7 (>=0.7 high), 0.39 (<0.4 low), 0.1 (low)
    recs = [_fake(10), _fake(7), _fake(4), _fake(1)]
    signal = retailer._compute_stock_signal(recs)
    levels = {s.product_name: s.demand_level for s in signal}
    assert levels["p-10"] == "high"
    assert levels["p-7"] == "high"
    assert levels["p-4"] == "medium"
    assert levels["p-1"] == "low"


# --- recommendation_log itself ----------------------------------------------

def test_recommendation_log_is_append_only_and_district_scoped(isolated_logs):
    recommendation_log.log_recommendation("Ludhiana", "A", 0.5)
    recommendation_log.log_recommendation("Amritsar", "B", 0.9)
    assert len(recommendation_log.get_recent_recommendations("Ludhiana")) == 1
    assert len(recommendation_log.get_recent_recommendations("Amritsar")) == 1
    assert recommendation_log.get_recent_recommendations("Nowhere") == []


# --- real wiring: recommend.py actually calls log_recommendation() ---------

def test_generate_recommendation_logs_to_recommendation_history(isolated_logs):
    from app.schemas.entry_point import FarmerRequest, LocationSchema
    from app.schemas.recommend import RecommendationRequest
    from app.services import recommend

    req = RecommendationRequest(
        farmer_request=FarmerRequest(
            crop="wheat",
            location=LocationSchema(district="Muktsar", state="Punjab"),
            symptom_description="stems hollow near base, seedlings dying",
            language="en",
            photo_present=False,
        )
    )
    result = recommend.generate_recommendation(req)
    assert result.no_confident_match is False, "test assumes a confident match to begin with"

    logged = recommendation_log.get_recent_recommendations("Muktsar")
    assert len(logged) == 1
    assert logged[0]["product_name"] == result.recommended_product


def test_generate_recommendation_does_not_log_a_no_confident_match(isolated_logs):
    from app.schemas.entry_point import FarmerRequest, LocationSchema
    from app.schemas.recommend import RecommendationRequest
    from app.services import recommend

    req = RecommendationRequest(
        farmer_request=FarmerRequest(
            crop="mango",  # off-catalog -> guaranteed no_confident_match
            location=LocationSchema(district="Ludhiana", state="Punjab"),
            symptom_description="leaves turning yellow",
            language="en",
            photo_present=False,
        )
    )
    result = recommend.generate_recommendation(req)
    assert result.no_confident_match is True
    assert recommendation_log.get_recent_recommendations("Ludhiana") == []
