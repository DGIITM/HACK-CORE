"""M3's readiness-score logic — deterministic, no external API needed for
these (compute_readiness and pests_active_within_window are pure
functions), plus the unknown-district and honest-fallback cases for the
full assess_risk() pipeline.
"""
import pytest

from app.schemas.entry_point import FarmerRequest, LocationSchema
from app.services import risk_context


# --- compute_readiness(): pure, across every combination -------------------

@pytest.mark.parametrize(
    "rain_penalty,soil_known,pest_active,expected_score,expected_proceed",
    [
        (False, False, False, 0, True),
        (False, False, True, 2, True),
        (False, True, False, 1, True),
        (False, True, True, 3, True),
        (True, False, False, -2, False),
        (True, False, True, 0, True),
        (True, True, False, -1, False),
        (True, True, True, 1, True),
    ],
)
def test_compute_readiness_across_all_combinations(rain_penalty, soil_known, pest_active, expected_score, expected_proceed):
    score, should_proceed = risk_context.compute_readiness(rain_penalty, soil_known, pest_active)
    assert score == expected_score
    assert should_proceed == expected_proceed


def test_compute_readiness_should_proceed_is_score_non_negative():
    for rain in (True, False):
        for soil in (True, False):
            for pest in (True, False):
                score, should_proceed = risk_context.compute_readiness(rain, soil, pest)
                assert should_proceed == (score >= 0)


# --- pests_active_within_window(): pure, deterministic month injection -----

_YELLOW_RUST_JAN = [{"district": "Gurdaspur", "crop": "wheat", "pest": "yellow rust", "typical_month": "January", "severity": "high"}]


def test_pest_active_on_exact_month_match():
    active = risk_context.pests_active_within_window(_YELLOW_RUST_JAN, current_month=1)
    assert len(active) == 1


def test_pest_active_within_one_month_window():
    active_before = risk_context.pests_active_within_window(_YELLOW_RUST_JAN, current_month=12)
    active_after = risk_context.pests_active_within_window(_YELLOW_RUST_JAN, current_month=2)
    assert len(active_before) == 1
    assert len(active_after) == 1


def test_pest_wraparound_december_to_january_counts_as_adjacent():
    """December (12) and January (1) are calendar-adjacent, not 11
    months apart — the circular distance calculation must reflect that."""
    active = risk_context.pests_active_within_window(_YELLOW_RUST_JAN, current_month=12)
    assert len(active) == 1


def test_pest_outside_window_is_not_active():
    active = risk_context.pests_active_within_window(_YELLOW_RUST_JAN, current_month=8)
    assert active == []


def test_pest_far_outside_window_is_not_active():
    active = risk_context.pests_active_within_window(_YELLOW_RUST_JAN, current_month=6)
    assert active == []


def test_empty_pest_list_returns_empty():
    assert risk_context.pests_active_within_window([], current_month=1) == []


def test_malformed_month_name_is_skipped_not_crashed():
    bad_row = [{"district": "X", "crop": "wheat", "pest": "mystery bug", "typical_month": "Not A Month", "severity": "low"}]
    assert risk_context.pests_active_within_window(bad_row, current_month=1) == []


# --- assess_risk(): unknown district ----------------------------------------

def _farmer_request(district: str, crop: str = "wheat") -> FarmerRequest:
    return FarmerRequest(
        crop=crop,
        location=LocationSchema(district=district, state="Punjab"),
        symptom_description="test",
        language="en",
        photo_present=False,
    )


def test_unknown_district_returns_honest_neutral_response():
    result = risk_context.assess_risk(_farmer_request("Nowhere District"))
    assert result.readiness_score == 0
    assert result.should_proceed is True
    assert result.active_pests == []
    assert result.early_warning is None
    assert "no data available" in result.weather_summary


def test_known_district_returns_real_shape():
    result = risk_context.assess_risk(_farmer_request("Ludhiana"))
    assert isinstance(result.readiness_score, int)
    assert isinstance(result.should_proceed, bool)
    assert isinstance(result.active_pests, list)
    if not result.should_proceed:
        assert result.early_warning is not None
    else:
        assert result.early_warning is None


def test_early_warning_is_null_when_should_proceed_is_true():
    # Bathinda has no logged wheat pests in typical off-season months and
    # a district we have real soil data for — likely (not guaranteed,
    # since real weather varies) to proceed; the contract invariant we
    # actually care about is checked regardless of which branch fires.
    result = risk_context.assess_risk(_farmer_request("Bathinda"))
    assert (result.early_warning is None) == result.should_proceed


# --- early-warning text generation (real fallback path, no GCP creds) ------

def test_early_warning_fallback_mentions_rain_when_that_was_the_reason():
    text = risk_context._build_early_warning_fallback(
        ["heavy rain is expected in the next few days, which can wash off a freshly applied product"]
    )
    assert "rain" in text.lower()


def test_early_warning_fallback_handles_no_specific_reasons():
    text = risk_context._build_early_warning_fallback([])
    assert isinstance(text, str) and text


def test_generate_early_warning_uses_real_fallback_when_gemini_unconfigured():
    """This dev sandbox has no GOOGLE_CLOUD_PROJECT configured, so this
    exercises the real fallback path end to end."""
    text = risk_context._generate_early_warning(["heavy rain expected"], _farmer_request("Ludhiana"))
    assert isinstance(text, str) and "rain" in text.lower()


def test_a_live_api_failure_falls_back_gracefully_instead_of_crashing(monkeypatch):
    """Regression: a real Gemini call that fails after credentials were
    valid (rate limit, network error, etc.) used to propagate as an
    unhandled exception — this module only caught 'not configured'."""
    from app.services import llm_service

    def _boom(*args, **kwargs):
        raise llm_service.LLMCallFailedError("simulated 429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(llm_service, "generate_response", _boom)
    text = risk_context._generate_early_warning(["heavy rain expected"], _farmer_request("Ludhiana"))
    assert isinstance(text, str) and "rain" in text.lower()
