"""M3 Risk Intelligence route — thin HTTP layer, no logic here."""
from fastapi import APIRouter

from app.schemas.entry_point import FarmerRequest
from app.schemas.risk_context import RiskContext
from app.services import risk_context as risk_context_service

router = APIRouter()


@router.post("/risk-context", response_model=RiskContext)
def risk_context(payload: FarmerRequest) -> RiskContext:
    return risk_context_service.assess_risk(payload)
