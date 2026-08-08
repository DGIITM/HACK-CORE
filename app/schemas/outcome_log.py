"""M7 Application & Logging — shapes for /log-outcome.

OutcomeLog is the exact contract from CLAUDE.md's "Outcome log
(M7 output)" section.
"""
from pydantic import BaseModel


class OutcomeLogInput(BaseModel):
    farmer_id: str
    product_used: str
    batch_verified: bool = True
    application_date: str
    observed_outcome: str
    yield_result: float


class OutcomeLog(BaseModel):
    farmer_id: str
    product_used: str
    batch_verified: bool
    application_date: str
    observed_outcome: str
    yield_result: float
    synced: bool
