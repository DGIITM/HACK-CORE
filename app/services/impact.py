"""M8 Impact Measurement — causal attribution -> ROI in rupees/acre.

Depth piece #2. Hard constraint from CLAUDE.md: never overclaim precision
— always report a range, never a single confident number.

M7 (Application & Logging) doesn't persist real outcome logs yet, so
there's no per-farmer data to attribute yet. Until it does, this returns
the difference-in-differences model's current population-level estimate
for the product overall (fit on the synthetic panel in impact_data.py),
not a per-farmer causal estimate — req.farmer_id / req.product_used are
accepted for API-contract stability but can't meaningfully filter
anything real yet. That's honest given what data actually exists; the
data itself is synthetic (see impact_data.py's documented ground truth),
but the DiD *model* running on it is real, same distinction M2 already
established for its own placeholder data.
"""
import json
import logging

from app.schemas.impact import ImpactEstimate, ImpactRequest
from app.services import impact_data, llm_service

logger = logging.getLogger(__name__)

# STUB: M9 (Feedback Loop) would eventually feed real outcome logs back
# into this model once M7 exists, replacing the synthetic panel below.

SYSTEM_PROMPT = """You are KrishiSathi's impact-reporting assistant.

You are given already-computed statistical results from a
difference-in-differences causal model. Your ONLY job is to package these
into the exact JSON response shape below — do not recompute, reinterpret,
adjust, or "improve" any of the numbers. Never present a more precise or
more confident number than what you were given; if anything, round
conservatively rather than invent extra precision.

Respond with ONLY a JSON object, no markdown fences, no extra commentary:
{"estimated_effect_pct": number, "confidence_range": [number, number],
"roi_per_acre_inr": integer, "nitrogen_saved_kg": integer,
"data_basis": "simulated"}
"""


def _compute_estimate() -> dict:
    result = impact_data.get_or_fit_did_result()

    roi_per_acre_inr = round(result.estimated_effect_abs * impact_data.WHEAT_MSP_INR_PER_QUINTAL)

    # Illustrative assumption, not independently measured: nitrogen savings
    # scale roughly with yield-efficiency gains, at ~1.5 kg N saved per 1%
    # effect — loosely proportioned against typical Punjab wheat nitrogen
    # application of ~120-150 kg/acre (PAU package of practices). This is
    # a modeling stand-in until real agronomic nitrogen-offset data exists.
    nitrogen_saved_kg = round(result.estimated_effect_pct * 1.5)

    return {
        "estimated_effect_pct": result.estimated_effect_pct,
        "confidence_range": result.confidence_range_pct,
        "roi_per_acre_inr": roi_per_acre_inr,
        "nitrogen_saved_kg": nitrogen_saved_kg,
        "data_basis": "simulated",
    }


def _build_user_prompt(computed: dict) -> str:
    return (
        "Computed results (package these, do not change the numbers):\n"
        f"{json.dumps(computed)}"
    )


def _numbers_match(a, b, tolerance: float) -> bool:
    try:
        return abs(float(a) - float(b)) <= tolerance
    except (TypeError, ValueError):
        return False


def _validate_narration(llm_output: dict, computed: dict) -> dict:
    """The safety net for this module: whatever Gemini returns, every
    numeric field is checked against the actual computed statistical
    result within a small tolerance. Anything that doesn't check out is
    replaced with the real computed value — Gemini may format, never
    alter, the numbers. data_basis is always forced to "simulated"
    regardless of what comes back, since that label is a compliance
    fact, not something an LLM gets to decide.
    """
    if not isinstance(llm_output, dict):
        return computed

    result = dict(computed)

    if _numbers_match(llm_output.get("estimated_effect_pct"), computed["estimated_effect_pct"], tolerance=0.5):
        result["estimated_effect_pct"] = round(float(llm_output["estimated_effect_pct"]), 1)

    llm_range = llm_output.get("confidence_range")
    if (
        isinstance(llm_range, list)
        and len(llm_range) == 2
        and _numbers_match(llm_range[0], computed["confidence_range"][0], tolerance=0.5)
        and _numbers_match(llm_range[1], computed["confidence_range"][1], tolerance=0.5)
    ):
        result["confidence_range"] = [round(float(llm_range[0]), 1), round(float(llm_range[1]), 1)]

    if _numbers_match(llm_output.get("roi_per_acre_inr"), computed["roi_per_acre_inr"], tolerance=50):
        result["roi_per_acre_inr"] = round(float(llm_output["roi_per_acre_inr"]))

    if _numbers_match(llm_output.get("nitrogen_saved_kg"), computed["nitrogen_saved_kg"], tolerance=2):
        result["nitrogen_saved_kg"] = round(float(llm_output["nitrogen_saved_kg"]))

    result["data_basis"] = "simulated"
    return result


def measure_impact(req: ImpactRequest) -> ImpactEstimate:
    computed = _compute_estimate()

    try:
        raw = llm_service.generate_response(
            prompt=_build_user_prompt(computed),
            system_prompt=SYSTEM_PROMPT,
            json_mode=True,
        )
        llm_output = json.loads(llm_service.extract_json_object(raw))
        final = _validate_narration(llm_output, computed)
    except llm_service.LLMNotConfiguredError:
        final = computed
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Gemini impact narration could not be parsed, using computed values: %s", exc)
        final = computed

    return ImpactEstimate(**final)
