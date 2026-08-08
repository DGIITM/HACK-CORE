"""M8 Impact Measurement — shapes for /measure-impact.

ImpactEstimate is the exact contract from CLAUDE.md's "Impact estimate
(M8 output)" section. This is the other depth piece (hard constraint #2:
report ranges, never a single overclaimed number).
"""
from typing import List, Optional

from pydantic import BaseModel


class ImpactRequest(BaseModel):
    farmer_id: str
    product_used: Optional[str] = None


class ImpactEstimate(BaseModel):
    estimated_effect_pct: float
    confidence_range: List[float]
    roi_per_acre_inr: int
    nitrogen_saved_kg: int
    data_basis: str
