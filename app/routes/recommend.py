"""M4 Recommendation Engine route — thin HTTP layer, no logic here."""
from fastapi import APIRouter

from app.schemas.recommend import Recommendation, RecommendationRequest
from app.services import recommend as recommend_service

router = APIRouter()


@router.post("/recommend", response_model=Recommendation)
def recommend(payload: RecommendationRequest) -> Recommendation:
    return recommend_service.generate_recommendation(payload)
