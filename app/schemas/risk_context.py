"""M3 Risk Intelligence — shapes for /risk-context.

RiskContext is the exact contract from CLAUDE.md's "Risk context
(M3 output)" section.
"""
from typing import List, Optional

from pydantic import BaseModel


class RiskContext(BaseModel):
    readiness_score: int
    should_proceed: bool
    weather_summary: str
    active_pests: List[str]
    early_warning: Optional[str] = None
