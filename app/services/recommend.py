"""M4 Recommendation Engine — retrieval + constrained reasoning.

Depth piece #1. Hard constraint from CLAUDE.md: the engine must NEVER
invent a product — retrieval returns candidates, the model may only pick
from those candidates, and if nothing fits well it must say so honestly
via no_confident_match rather than forcing a pick. Even this stub respects
that shape: it only ever returns something drawn from the catalog.
"""
import random

from app.schemas.recommend import NeighbourProof, Recommendation, RecommendationRequest
from app.services import data_foundation


def generate_recommendation(req: RecommendationRequest) -> Recommendation:
    # STUB: real logic runs a Qdrant similarity search over the efficacy
    # dataset using crop + symptom_description + active_pests as the query,
    # then a constrained Gemini call that must select only from the
    # retrieved candidates (or set no_confident_match=True honestly).
    candidates = data_foundation.get_product_catalog()
    product = random.choice(candidates)

    confidence_score = round(random.uniform(0.55, 0.92), 2)
    no_confident_match = confidence_score < 0.6

    return Recommendation(
        recommended_product=product["name"],
        confidence_score=confidence_score,
        plain_language_reason=(
            f"Farmers with similar symptoms on {req.farmer_request.crop} nearby saw "
            "improvement with this product within a few weeks."
        ),
        mode_of_action=product["mode_of_action"],
        neighbour_proof=NeighbourProof(
            farmers_nearby=random.randint(5, 25),
            avg_outcome=f"{random.randint(5, 15)}% yield improvement",
            available=True,
        ),
        no_confident_match=no_confident_match,
    )
