"""M9 Feedback Loop — outcomes sharpen future recommendations.

"A simple running average... does not need to be a retraining pipeline
— arithmetic is enough" (CLAUDE.md). get_confidence_boost() reads real
M7 outcome logs (via outcome_store.get_outcomes(), added here since it
didn't already exist despite earlier notes assuming it did — verified
by reading outcome_store.py directly rather than assuming) and M8's
small per-(product, district) estimate history (added in impact.py's
_persist_estimate/get_recent_estimates), and turns them into a small,
capped confidence adjustment for M4.

No HTTP route: this is consumed directly by recommend.py's
generate_recommendation(), and get_retailer_evidence() below is built
ahead of M6 needing it, same pattern M7 used when it built
get_outcomes() ahead of M8/M9 needing it.
"""
from typing import Dict, List, Optional

from app.services import impact, impact_data, outcome_store

# A logged outcome counts as "positive" if its yield_result beats the
# same baseline M8's synthetic panel uses (~21 quintals/acre, grounded in
# PAU's real Punjab average — see impact_data.py). Simple, arithmetic,
# and reuses the one already-documented number rather than inventing a
# second baseline.
POSITIVE_OUTCOME_YIELD_THRESHOLD = impact_data.BASE_YIELD_QUINTALS_PER_ACRE

BOOST_PER_POSITIVE_OUTCOME = 0.02
MAX_OUTCOME_BOOST = 0.08
# Small extra nudge if M8's own causal estimate for this product/district
# also shows a positive effect — a second, independent real signal
# corroborating the outcome-count boost above.
IMPACT_CORROBORATION_BOOST = 0.02
MAX_TOTAL_BOOST = 0.10


def _is_positive_outcome(outcome: Dict) -> bool:
    try:
        return float(outcome.get("yield_result", 0)) > POSITIVE_OUTCOME_YIELD_THRESHOLD
    except (TypeError, ValueError):
        return False


def get_confidence_boost(product_name: str, district: Optional[str] = None) -> float:
    """Small, capped confidence adjustment for M4 — never dominates the
    base score, and is exactly zero when there's no real outcome data
    yet for this product/region, never a fabricated guess.
    """
    outcomes = outcome_store.get_outcomes(product_name, district)
    positive_count = sum(1 for o in outcomes if _is_positive_outcome(o))
    outcome_boost = min(positive_count * BOOST_PER_POSITIVE_OUTCOME, MAX_OUTCOME_BOOST)

    recent_estimates = impact.get_recent_estimates(product_name, district)
    corroboration_boost = (
        IMPACT_CORROBORATION_BOOST
        if any(e.get("estimated_effect_pct", 0) > 0 for e in recent_estimates)
        else 0.0
    )

    return round(min(outcome_boost + corroboration_boost, MAX_TOTAL_BOOST), 4)


def get_retailer_evidence(district: str) -> Dict:
    """Summarizes real M7 outcome logs (and, where available, M8
    estimates) for a district — this becomes M6's data source next. Not
    consumed by any endpoint yet, same "build it ahead of the module
    that needs it" pattern M7 used for get_outcomes().

    Recommendation-history aggregation (counts/avg confidence per
    product) isn't included here — M4 doesn't persist any recommendation
    history yet, and that's explicitly M6's own first build step, not
    M9's.
    """
    district_outcomes = outcome_store.get_outcomes_by_district(district)

    products = sorted({o["product_used"] for o in district_outcomes if o.get("product_used")})
    product_summaries: List[Dict] = []
    for product_name in products:
        product_outcomes = [o for o in district_outcomes if o.get("product_used") == product_name]
        positive_count = sum(1 for o in product_outcomes if _is_positive_outcome(o))
        product_summaries.append(
            {
                "product_name": product_name,
                "outcomes_logged": len(product_outcomes),
                "positive_outcomes": positive_count,
                "confidence_boost": get_confidence_boost(product_name, district),
            }
        )

    return {
        "district": district,
        "products": product_summaries,
        "total_outcomes_logged": len(district_outcomes),
    }
