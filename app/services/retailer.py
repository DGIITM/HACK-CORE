"""M6 Retailer Console — district view of recommendations + evidence.

Aggregates M4's own recommendation log (app/services/recommendation_log.py
— added there specifically for this, same "build it ahead of the module
that needs it" pattern M7/M9 already used) by product, and pulls real
outcome evidence from M9's get_retailer_evidence() to honestly report
outcomes_logged / avg_outcome_summary — "no outcomes logged yet for this
product in this area" rather than inventing a number when there's
nothing to report.

stock_signal is plain frequency-based aggregation, explicitly NOT a
forecasting model, per CLAUDE.md.
"""
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List

from app.schemas.retailer import RecentRecommendation, RetailerConsoleResponse, StockSignalEntry
from app.services import feedback_loop, recommendation_log

# Judgment call, documented: demand_level is relative to this district's
# own busiest product, not an absolute count threshold — meaningful
# whether a district has 3 logged recommendations or 300.
HIGH_DEMAND_RATIO = 0.7
MEDIUM_DEMAND_RATIO = 0.4


def _aggregate_recommendations(district: str) -> List[RecentRecommendation]:
    rows = recommendation_log.get_recent_recommendations(district)

    by_product: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        by_product[row["product_name"]].append(row)

    evidence = feedback_loop.get_retailer_evidence(district)
    evidence_by_product = {p["product_name"]: p for p in evidence["products"]}

    summaries = []
    for product_name, product_rows in by_product.items():
        count = len(product_rows)
        avg_confidence = sum(r["confidence_score"] for r in product_rows) / count

        product_evidence = evidence_by_product.get(product_name)
        if product_evidence and product_evidence["outcomes_logged"] > 0:
            outcomes_logged = product_evidence["outcomes_logged"]
            avg_outcome_summary = (
                f"{product_evidence['positive_outcomes']} of {outcomes_logged} logged "
                "outcomes above the district baseline"
            )
        else:
            outcomes_logged = 0
            avg_outcome_summary = "no outcomes logged yet for this product in this area"

        summaries.append(
            RecentRecommendation(
                product_name=product_name,
                count=count,
                avg_confidence=round(avg_confidence, 2),
                outcomes_logged=outcomes_logged,
                avg_outcome_summary=avg_outcome_summary,
            )
        )

    summaries.sort(key=lambda r: r.count, reverse=True)
    return summaries


def _compute_stock_signal(recent_recommendations: List[RecentRecommendation]) -> List[StockSignalEntry]:
    if not recent_recommendations:
        return []

    max_count = max(r.count for r in recent_recommendations)
    signal = []
    for r in recent_recommendations:
        ratio = r.count / max_count
        if ratio >= HIGH_DEMAND_RATIO:
            demand_level = "high"
        elif ratio >= MEDIUM_DEMAND_RATIO:
            demand_level = "medium"
        else:
            demand_level = "low"
        signal.append(StockSignalEntry(product_name=r.product_name, demand_level=demand_level))
    return signal


def get_district_console(district: str) -> RetailerConsoleResponse:
    recent_recommendations = _aggregate_recommendations(district)
    stock_signal = _compute_stock_signal(recent_recommendations)

    return RetailerConsoleResponse(
        district=district,
        recent_recommendations=recent_recommendations,
        stock_signal=stock_signal,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
