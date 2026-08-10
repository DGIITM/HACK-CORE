"""M9: the running-average confidence boost, the M8 estimate persistence
it also reads from, and get_retailer_evidence(). Every test gets an
isolated SQLite file (mirroring M7's own test pattern) and a reset
in-memory M8 estimate store, so runs don't leak state between tests or
into the real dev database.
"""
import pytest

from app.schemas.impact import ImpactRequest
from app.schemas.outcome_log import OutcomeLogInput
from app.services import feedback_loop, impact, outcome_log, outcome_store


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(outcome_store, "DB_PATH", tmp_path / "outcome_log_cache.sqlite3")
    return outcome_store


@pytest.fixture(autouse=True)
def reset_impact_estimates():
    impact._recent_estimates.clear()
    yield
    impact._recent_estimates.clear()


def _log(isolated_store, product="Trichoderma viride bio-fungicide", district="Ludhiana", yield_result=30.0, farmer="f-1"):
    return outcome_log.log_outcome(
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


# --- get_confidence_boost(): the zero-data honesty guarantee ---------------

def test_boost_is_exactly_zero_with_no_outcome_data(isolated_store):
    assert feedback_loop.get_confidence_boost("Some Product", "Ludhiana") == 0.0


def test_boost_is_exactly_zero_for_unrelated_product(isolated_store):
    _log(isolated_store, product="Trichoderma viride bio-fungicide", district="Ludhiana")
    assert feedback_loop.get_confidence_boost("A Totally Different Product", "Ludhiana") == 0.0


def test_boost_is_exactly_zero_for_unrelated_district(isolated_store):
    _log(isolated_store, product="Trichoderma viride bio-fungicide", district="Ludhiana")
    assert feedback_loop.get_confidence_boost("Trichoderma viride bio-fungicide", "Amritsar") == 0.0


# --- get_confidence_boost(): real math, deterministic ------------------------

def test_boost_increases_with_each_positive_outcome(isolated_store):
    product = "Trichoderma viride bio-fungicide"
    boosts = []
    for i in range(3):
        _log(isolated_store, product=product, district="Ludhiana", yield_result=30.0, farmer=f"f-{i}")
        boosts.append(feedback_loop.get_confidence_boost(product, "Ludhiana"))
    assert boosts == sorted(boosts)  # strictly non-decreasing
    assert boosts[-1] > boosts[0]


def test_boost_matches_expected_arithmetic(isolated_store):
    """3 positive outcomes * 0.02 per outcome = 0.06, under both caps —
    deterministic, no fuzz."""
    for i in range(3):
        _log(isolated_store, product="Trichoderma viride bio-fungicide", district="Ludhiana", yield_result=30.0, farmer=f"f-{i}")
    boost = feedback_loop.get_confidence_boost("Trichoderma viride bio-fungicide", "Ludhiana")
    assert boost == pytest.approx(0.06)


def test_boost_is_capped_and_never_dominates(isolated_store):
    product = "Trichoderma viride bio-fungicide"
    for i in range(50):
        _log(isolated_store, product=product, district="Ludhiana", yield_result=30.0, farmer=f"f-{i}")
    boost = feedback_loop.get_confidence_boost(product, "Ludhiana")
    assert boost <= feedback_loop.MAX_TOTAL_BOOST


def test_non_positive_outcomes_do_not_contribute(isolated_store):
    product = "Trichoderma viride bio-fungicide"
    # yield below the positive-outcome baseline
    for i in range(5):
        _log(isolated_store, product=product, district="Ludhiana", yield_result=5.0, farmer=f"f-{i}")
    assert feedback_loop.get_confidence_boost(product, "Ludhiana") == 0.0


def test_corroboration_boost_from_m8_positive_estimate(isolated_store):
    product = "Trichoderma viride bio-fungicide"
    impact.measure_impact(ImpactRequest(farmer_id="f-1", product_used=product, district="Ludhiana"))
    boost = feedback_loop.get_confidence_boost(product, "Ludhiana")
    assert boost == pytest.approx(feedback_loop.IMPACT_CORROBORATION_BOOST)


def test_outcome_and_corroboration_boosts_combine_but_stay_capped(isolated_store):
    product = "Trichoderma viride bio-fungicide"
    for i in range(5):
        _log(isolated_store, product=product, district="Ludhiana", yield_result=30.0, farmer=f"f-{i}")
    impact.measure_impact(ImpactRequest(farmer_id="f-1", product_used=product, district="Ludhiana"))
    boost = feedback_loop.get_confidence_boost(product, "Ludhiana")
    assert boost <= feedback_loop.MAX_TOTAL_BOOST
    assert boost > feedback_loop.MAX_OUTCOME_BOOST  # corroboration genuinely added something


# --- get_retailer_evidence(): honest aggregation, built ahead of M6 --------

def test_retailer_evidence_for_district_with_no_data_is_honest_and_well_formed(isolated_store):
    evidence = feedback_loop.get_retailer_evidence("Nowhere Logged")
    assert evidence["district"] == "Nowhere Logged"
    assert evidence["products"] == []
    assert evidence["total_outcomes_logged"] == 0


def test_retailer_evidence_aggregates_real_logged_outcomes(isolated_store):
    product = "Trichoderma viride bio-fungicide"
    _log(isolated_store, product=product, district="Ludhiana", yield_result=30.0, farmer="f-1")
    _log(isolated_store, product=product, district="Ludhiana", yield_result=5.0, farmer="f-2")

    evidence = feedback_loop.get_retailer_evidence("Ludhiana")
    assert evidence["total_outcomes_logged"] == 2
    assert len(evidence["products"]) == 1
    summary = evidence["products"][0]
    assert summary["product_name"] == product
    assert summary["outcomes_logged"] == 2
    assert summary["positive_outcomes"] == 1


def test_retailer_evidence_only_includes_the_requested_district(isolated_store):
    _log(isolated_store, product="Trichoderma viride bio-fungicide", district="Ludhiana", farmer="f-1")
    _log(isolated_store, product="Trichoderma viride bio-fungicide", district="Amritsar", farmer="f-2")

    evidence = feedback_loop.get_retailer_evidence("Ludhiana")
    assert evidence["total_outcomes_logged"] == 1


# --- get_recent_estimates(): M8's minimal persistence ------------------------

def test_get_recent_estimates_empty_for_unknown_key():
    assert impact.get_recent_estimates("Never Requested", "Nowhere") == []


def test_get_recent_estimates_bounded_to_max_stored():
    for _ in range(impact.MAX_STORED_ESTIMATES_PER_KEY + 5):
        impact.measure_impact(ImpactRequest(farmer_id="f-1", product_used="Some Product", district="Ludhiana"))
    assert len(impact.get_recent_estimates("Some Product", "Ludhiana")) == impact.MAX_STORED_ESTIMATES_PER_KEY


def test_measure_impact_without_product_used_does_not_persist_anything():
    impact.measure_impact(ImpactRequest(farmer_id="f-1"))
    assert impact.get_recent_estimates("", None) == []


# --- The key test: the loop genuinely changes M4's confidence score --------

def test_recommendation_confidence_increases_with_real_positive_outcomes(isolated_store):
    """This is the 'does the loop actually work' test — equivalent to
    M8's recovery-of-known-effect test. Verified by hand before writing
    this: 0.61 -> 0.67 confidence for the same request after logging 3
    real positive outcomes for the recommended product/district."""
    from app.schemas.entry_point import FarmerRequest, LocationSchema
    from app.schemas.recommend import RecommendationRequest
    from app.services import recommend

    req = RecommendationRequest(
        farmer_request=FarmerRequest(
            crop="wheat",
            location=LocationSchema(district="Muktsar", state="Punjab"),
            symptom_description="pink stem borer caterpillar feeding on stems, seedlings dying",
            language="en",
            photo_present=False,
        )
    )

    before = recommend.generate_recommendation(req)
    assert before.no_confident_match is False, "test assumes a confident match to begin with"

    for i in range(3):
        _log(isolated_store, product=before.recommended_product, district="Muktsar", yield_result=30.0, farmer=f"f-{i}")

    after = recommend.generate_recommendation(req)

    assert after.recommended_product == before.recommended_product
    assert after.confidence_score > before.confidence_score


def test_recommendation_confidence_boost_never_flips_no_confident_match(isolated_store):
    """Guardrail exercised through the real pipeline, not a hand-built
    object: a crop not in the catalog (one of M4's own adversarial cases)
    gates to zero retrieval candidates before any query text is even
    considered, so it must still come back honest even with abundant
    positive outcome data logged for an unrelated, real product/district
    — the boost is only ever applied to an already-confident decision,
    never used to manufacture one.

    Note: earlier versions of this test used off-topic/gibberish symptom
    text instead of an off-catalog crop — those weren't reliably zero-
    candidate cases at the time, because retrieval.py used to fold
    active_pests directly into the query text, so a district's pest
    names alone could produce a confident-looking match regardless of
    what the symptom actually said (identical to the soil_type bug
    retrieval.py's own docstring already documented). That's since been
    fixed — active_pests is now a ranking bonus applied only after the
    symptom text clears the relevance gate on its own, same treatment as
    soil_type — but this test still uses an off-catalog crop rather than
    gibberish, since that's the more fundamental zero-candidate guarantee
    (retrieval's crop gate short-circuits before any query text is
    examined at all) and doesn't depend on the current state of the
    similarity gate's tuning.
    """
    from app.schemas.entry_point import FarmerRequest, LocationSchema
    from app.schemas.recommend import RecommendationRequest
    from app.services import recommend

    for i in range(10):
        _log(isolated_store, product="Trichoderma viride bio-fungicide", district="Ludhiana", yield_result=30.0, farmer=f"f-{i}")

    req = RecommendationRequest(
        farmer_request=FarmerRequest(
            crop="mango",
            location=LocationSchema(district="Ludhiana", state="Punjab"),
            symptom_description="leaves turning yellow at the tips",
            language="en",
            photo_present=False,
        )
    )
    result = recommend.generate_recommendation(req)
    assert result.no_confident_match is True
    assert result.recommended_product == ""
    assert result.confidence_score == 0.0


# --- _real_neighbour_proof(): the other stale STUB this pass closed out ----

def test_neighbour_proof_unavailable_with_no_outcome_data(isolated_store):
    from app.services.recommend import _real_neighbour_proof

    proof = _real_neighbour_proof("Trichoderma viride bio-fungicide", "Ludhiana")
    assert proof.available is False
    assert proof.farmers_nearby == 0


def test_neighbour_proof_reflects_real_logged_outcomes(isolated_store):
    from app.services.recommend import _real_neighbour_proof

    product = "Trichoderma viride bio-fungicide"
    _log(isolated_store, product=product, district="Ludhiana", yield_result=30.0, farmer="f-1")
    _log(isolated_store, product=product, district="Ludhiana", yield_result=10.0, farmer="f-2")

    proof = _real_neighbour_proof(product, "Ludhiana")
    assert proof.available is True
    assert proof.farmers_nearby == 2
    assert "2 logged" in proof.avg_outcome


def test_neighbour_proof_never_counts_a_different_districts_outcomes(isolated_store):
    from app.services.recommend import _real_neighbour_proof

    product = "Trichoderma viride bio-fungicide"
    _log(isolated_store, product=product, district="Amritsar", farmer="f-1")

    proof = _real_neighbour_proof(product, "Ludhiana")
    assert proof.available is False
    assert proof.farmers_nearby == 0


def test_generate_recommendation_surfaces_real_neighbour_proof_end_to_end(isolated_store):
    from app.schemas.entry_point import FarmerRequest, LocationSchema
    from app.schemas.recommend import RecommendationRequest
    from app.services import recommend

    req = RecommendationRequest(
        farmer_request=FarmerRequest(
            crop="wheat",
            location=LocationSchema(district="Muktsar", state="Punjab"),
            symptom_description="pink stem borer caterpillar feeding on stems, seedlings dying",
            language="en",
            photo_present=False,
        )
    )
    before = recommend.generate_recommendation(req)
    assert before.neighbour_proof.available is False

    for i in range(2):
        _log(isolated_store, product=before.recommended_product, district="Muktsar", yield_result=30.0, farmer=f"f-{i}")

    after = recommend.generate_recommendation(req)
    assert after.neighbour_proof.available is True
    assert after.neighbour_proof.farmers_nearby == 2
