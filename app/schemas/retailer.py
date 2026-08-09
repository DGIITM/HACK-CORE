"""M6 Retailer Console — shapes for /retailer.

Not part of CLAUDE.md's formal data contract, so this shape isn't
locked — replaces the earlier per-farmer-row skeleton design (which
matched nothing this module now actually aggregates) with a shape that
maps directly onto what M4's recommendation log and M9's outcome
evidence can genuinely produce: recent recommendation activity per
product, and a simple frequency-based stock signal.
"""
from typing import List

from pydantic import BaseModel


class RecentRecommendation(BaseModel):
    product_name: str
    count: int
    avg_confidence: float
    outcomes_logged: int
    avg_outcome_summary: str


class StockSignalEntry(BaseModel):
    product_name: str
    demand_level: str  # "high" | "medium" | "low" — plain aggregation, not a forecast


class RetailerConsoleResponse(BaseModel):
    district: str
    recent_recommendations: List[RecentRecommendation]
    stock_signal: List[StockSignalEntry]
    generated_at: str
