"""M4 Recommendation Engine — shapes for /recommend.

Recommendation is the exact contract from CLAUDE.md's "Recommendation
(M4 output)" section. This is one of the two depth pieces (hard
constraint #1: never invent a product outside retrieved candidates).
"""
from typing import Optional

from pydantic import BaseModel

from app.schemas.entry_point import FarmerRequest
from app.schemas.risk_context import EnvironmentalAssessment, RiskContext


class NeighbourProof(BaseModel):
    farmers_nearby: int
    avg_outcome: str
    available: bool


class Recommendation(BaseModel):
    recommended_product: str
    confidence_score: float
    plain_language_reason: str
    mode_of_action: str
    neighbour_proof: NeighbourProof
    no_confident_match: bool
    application_context: Optional[EnvironmentalAssessment] = None


class RecommendationRequest(BaseModel):
    farmer_request: FarmerRequest
    risk_context: Optional[RiskContext] = None