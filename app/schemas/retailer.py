"""M6 Retailer Console — shapes for /retailer.

Not part of CLAUDE.md's formal data contract, designed to match M6's
stated job: a district view of recommendations + evidence, including the
counterfeit-check trust feature.
"""
from typing import List

from pydantic import BaseModel


class RetailerEvidenceRow(BaseModel):
    farmer_id: str
    crop: str
    recommended_product: str
    confidence_score: float
    outcome_verified: bool
    counterfeit_flagged: bool


class RetailerConsoleResponse(BaseModel):
    district: str
    rows: List[RetailerEvidenceRow]
    counterfeit_alerts: int
