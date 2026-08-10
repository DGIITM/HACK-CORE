"""M8 service layer: measure_impact()'s output contract and the
_validate_narration safety net that stops Gemini from ever overriding the
actual computed statistical results (or the "simulated" data_basis label).
"""
from app.schemas.impact import ImpactRequest
from app.services import impact


def test_measure_impact_returns_exact_contract_shape():
    result = impact.measure_impact(ImpactRequest(farmer_id="sim-farmer-0001"))
    assert isinstance(result.estimated_effect_pct, float)
    assert len(result.confidence_range) == 2
    assert result.confidence_range[0] < result.confidence_range[1]
    assert isinstance(result.roi_per_acre_inr, int)
    assert isinstance(result.nitrogen_saved_kg, int)
    assert result.data_basis == "simulated"


def test_measure_impact_ignores_absent_farmer_id_gracefully():
    """No real M7 data exists yet, so farmer_id can't meaningfully filter
    anything — this should still return a valid population-level estimate,
    not crash or fabricate a farmer-specific number."""
    result = impact.measure_impact(ImpactRequest(farmer_id="does-not-exist"))
    assert result.data_basis == "simulated"
    assert len(result.confidence_range) == 2


_COMPUTED = {
    "estimated_effect_pct": 12.6,
    "confidence_range": [9.1, 16.1],
    "roi_per_acre_inr": 6400,
    "nitrogen_saved_kg": 19,
    "data_basis": "simulated",
}


def test_validator_accepts_narration_matching_computed_values():
    llm_output = dict(_COMPUTED)
    result = impact._validate_narration(llm_output, _COMPUTED)
    assert result == _COMPUTED


def test_validator_overrides_wildly_different_effect_estimate():
    llm_output = dict(_COMPUTED, estimated_effect_pct=45.0)
    result = impact._validate_narration(llm_output, _COMPUTED)
    assert result["estimated_effect_pct"] == _COMPUTED["estimated_effect_pct"]


def test_validator_overrides_wildly_different_confidence_range():
    llm_output = dict(_COMPUTED, confidence_range=[30.0, 60.0])
    result = impact._validate_narration(llm_output, _COMPUTED)
    assert result["confidence_range"] == _COMPUTED["confidence_range"]


def test_validator_never_lets_data_basis_be_overridden():
    """The one field an LLM must never get to change — this is a
    compliance label, not a narration choice."""
    llm_output = dict(_COMPUTED, data_basis="real")
    result = impact._validate_narration(llm_output, _COMPUTED)
    assert result["data_basis"] == "simulated"


def test_validator_falls_back_to_computed_on_malformed_output():
    result = impact._validate_narration("not even a dict", _COMPUTED)
    assert result == _COMPUTED


def test_validator_falls_back_on_missing_fields():
    result = impact._validate_narration({}, _COMPUTED)
    assert result["data_basis"] == "simulated"
    assert result["estimated_effect_pct"] == _COMPUTED["estimated_effect_pct"]


def test_validator_accepts_small_rounding_differences():
    """Gemini reformatting/rounding slightly shouldn't be rejected — only
    genuine deviations should trigger the override."""
    llm_output = dict(_COMPUTED, estimated_effect_pct=12.7, roi_per_acre_inr=6420)
    result = impact._validate_narration(llm_output, _COMPUTED)
    assert result["estimated_effect_pct"] == 12.7
    assert result["roi_per_acre_inr"] == 6420


def test_a_live_api_failure_falls_back_gracefully_instead_of_crashing(monkeypatch):
    """Regression: a real Gemini call that fails after credentials were
    valid (rate limit, network error, etc.) used to propagate as an
    unhandled exception — measure_impact() only caught 'not configured'."""
    from app.services import llm_service

    def _boom(*args, **kwargs):
        raise llm_service.LLMCallFailedError("simulated 429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(llm_service, "generate_response", _boom)
    result = impact.measure_impact(ImpactRequest(farmer_id="f-1"))
    assert result.data_basis == "simulated"
    assert len(result.confidence_range) == 2
