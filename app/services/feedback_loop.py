"""M9 Feedback Loop — outcomes sharpen future recommendations.

No HTTP route: this module consumes M8's output internally and feeds back
into M4 (recommendation confidence/retrieval weighting) and M6 (retailer
evidence view). Nothing calls this yet in the skeleton pass.
"""
from app.schemas.impact import ImpactEstimate


def update_recommendation_weights(impact_estimate: ImpactEstimate) -> None:
    # STUB: real logic re-weights M4's retrieval/confidence scoring based
    # on accumulated M8 impact estimates, and pushes verified/failed
    # outcomes back into M6's district evidence view. Deferred until M4
    # and M8 are real — a stub can't meaningfully "learn" from fake data.
    raise NotImplementedError("M9: feedback loop not yet built")
