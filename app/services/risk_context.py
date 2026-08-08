"""M3 Risk Intelligence — weather, soil, pest history -> readiness score."""
import random

from app.schemas.entry_point import FarmerRequest
from app.schemas.risk_context import RiskContext
from app.services import data_foundation


def assess_risk(farmer_request: FarmerRequest) -> RiskContext:
    # STUB: real logic pulls a live rain forecast, simulated IoT soil
    # sensor readings, and BigQuery regional pest history, then combines
    # them into a readiness_score and a should_proceed decision (e.g. don't
    # recommend spraying right before heavy rain washes the product off).
    active_pests = data_foundation.get_pest_history(farmer_request.location.district)
    readiness_score = random.randint(1, 5)

    return RiskContext(
        readiness_score=readiness_score,
        should_proceed=readiness_score >= 3,
        weather_summary="no heavy rain expected for 5 days",
        active_pests=active_pests,
        early_warning=None if readiness_score >= 3 else "heavy rain expected in the next 48 hours",
    )
