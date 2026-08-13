"""M3 Risk Intelligence route — thin HTTP layer, no logic here."""
from fastapi import APIRouter

from app.schemas.risk_context import RiskContext, RiskRequest
from app.services import risk_context as risk_context_service

router = APIRouter()


@router.post("/risk-context", response_model=RiskContext)
def risk_context(payload: RiskRequest) -> RiskContext:
    return risk_context_service.assess_risk(payload)
