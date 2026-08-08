"""M8 Impact Measurement route — thin HTTP layer, no logic here."""
from fastapi import APIRouter

from app.schemas.impact import ImpactEstimate, ImpactRequest
from app.services import impact as impact_service

router = APIRouter()


@router.post("/measure-impact", response_model=ImpactEstimate)
def measure_impact(payload: ImpactRequest) -> ImpactEstimate:
    return impact_service.measure_impact(payload)
