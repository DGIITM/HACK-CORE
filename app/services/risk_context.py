"""M3 Risk Intelligence — weather, soil, pest history -> readiness score.

Rules-based, not a trained model, per CLAUDE.md. The whole score in one
sentence: start at zero, drop 2 if heavy rain is forecast (it can wash
off a freshly applied product), add 1 if we have real soil data for this
district, add 2 if there's a regionally-active pest for this crop around
now, and proceed if the total isn't negative.

Unknown-district handling: M2's get_soil_type(district) returning None
is the "we have no data for this place" signal (soil_type_by_district.json
covers the same districts weather_service has coordinates for) — that
short-circuits to an honest neutral response rather than silently
guessing a location's weather or fabricating pest/soil data.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from app.schemas.entry_point import FarmerRequest
from app.schemas.risk_context import RiskContext
from app.services import data_foundation, llm_service, weather_service

logger = logging.getLogger(__name__)

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# A single "typical_month" label is inherently approximate — real pest
# emergence spans weeks around it — so treat anything within one month
# (circular, so December-January count as adjacent) as "active now"
# rather than requiring an exact calendar match. Documented judgment call.
PEST_MONTH_WINDOW = 1

EARLY_WARNING_SYSTEM_PROMPT = (
    "You are KrishiSathi's risk advisor. Write exactly one short, plain-language "
    "sentence for a farmer with no agricultural training, telling them it's better "
    "to wait a few days before acting and briefly why. No jargon, no chemical names, "
    "no markdown, no quotation marks."
)


def _month_distance(month_a: int, month_b: int) -> int:
    diff = abs(month_a - month_b)
    return min(diff, 12 - diff)


def pests_active_within_window(
    pests_detail: List[Dict], current_month: Optional[int] = None, window: int = PEST_MONTH_WINDOW
) -> List[Dict]:
    """Pest rows whose typical_month falls within `window` months of
    `current_month` (1-12; defaults to the real current month). Pure and
    deterministic when current_month is passed explicitly — that's what
    makes this unit-testable without depending on the system clock.
    """
    if current_month is None:
        current_month = datetime.now().month

    active = []
    for row in pests_detail:
        try:
            row_month = _MONTH_NAMES.index(row["typical_month"]) + 1
        except ValueError:
            continue
        if _month_distance(row_month, current_month) <= window:
            active.append(row)
    return active


def compute_readiness(rain_penalty_applied: bool, soil_known: bool, pest_active: bool) -> Tuple[int, bool]:
    """The pure scoring rule, isolated from all I/O so it's trivially
    testable across every combination of inputs."""
    score = 0
    if rain_penalty_applied:
        score -= 2
    if soil_known:
        score += 1
    if pest_active:
        score += 2
    return score, score >= 0


def _build_early_warning_fallback(reasons: List[str]) -> str:
    """Deterministic, real fallback — not a stub. Used directly when
    Vertex AI isn't configured (this dev sandbox has no GCP credentials,
    same situation every other module's LLM call has hit), and as the
    safety net if Gemini's response is somehow empty."""
    if not reasons:
        return "Conditions don't look ideal right now, so it may be worth waiting a few days before acting."
    return "Right now isn't ideal: " + "; ".join(reasons) + " — it's worth waiting a few days before acting."


def _generate_early_warning(reasons: List[str], farmer_request: FarmerRequest) -> str:
    fallback = _build_early_warning_fallback(reasons)
    try:
        raw = llm_service.generate_response(
            prompt=(
                f"Crop: {farmer_request.crop}. District: {farmer_request.location.district}.\n"
                f"Reasons conditions aren't ideal right now: "
                f"{'; '.join(reasons) if reasons else 'general uncertainty'}."
            ),
            system_prompt=EARLY_WARNING_SYSTEM_PROMPT,
        )
        text = raw.strip().strip('"')
        return text or fallback
    except llm_service.LLMNotConfiguredError:
        logger.warning(
            "Vertex AI Gemini isn't configured in this environment — using a templated early_warning instead."
        )
        return fallback


def assess_risk(farmer_request: FarmerRequest) -> RiskContext:
    district = farmer_request.location.district
    crop = farmer_request.crop

    soil_type = data_foundation.get_soil_type(district)
    soil_known = soil_type is not None

    if not soil_known:
        logger.info("District %r has no data in M2's tables — returning an honest neutral RiskContext.", district)
        return RiskContext(
            readiness_score=0,
            should_proceed=True,
            weather_summary="no data available for this district — showing a neutral default rather than a guess",
            active_pests=[],
            early_warning=None,
        )

    pests_detail = data_foundation.get_pest_history_detail(district, crop)
    active_now = pests_active_within_window(pests_detail)
    forecast = weather_service.get_forecast(district)

    rain_penalty_applied = (not forecast.is_fallback) and forecast.rain_mm is not None and forecast.rain_mm > weather_service.RAIN_THRESHOLD_MM

    score, should_proceed = compute_readiness(
        rain_penalty_applied=rain_penalty_applied, soil_known=soil_known, pest_active=bool(active_now)
    )

    early_warning = None
    if not should_proceed:
        reasons = []
        if rain_penalty_applied:
            reasons.append("heavy rain is expected in the next few days, which can wash off a freshly applied product")
        if not active_now:
            reasons.append("there's no strong regional pest signal for this crop right now either")
        early_warning = _generate_early_warning(reasons, farmer_request)

    return RiskContext(
        readiness_score=score,
        should_proceed=should_proceed,
        weather_summary=forecast.summary,
        active_pests=[row["pest"] for row in active_now],
        early_warning=early_warning,
    )
