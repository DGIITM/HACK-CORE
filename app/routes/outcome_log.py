"""M7 Application & Logging route — thin HTTP layer, no logic here."""
from fastapi import APIRouter

from app.schemas.outcome_log import OutcomeLog, OutcomeLogInput
from app.services import outcome_log as outcome_log_service

router = APIRouter()


@router.post("/log-outcome", response_model=OutcomeLog)
def log_outcome(payload: OutcomeLogInput) -> OutcomeLog:
    return outcome_log_service.log_outcome(payload)
