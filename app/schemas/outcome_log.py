"""M7 Application & Logging — shapes for /log-outcome.

OutcomeLog is the exact contract from CLAUDE.md's "Outcome log
(M7 output)" section — that shape is locked. OutcomeLogInput isn't part
of CLAUDE.md's data contract, so it's free to change here: it now takes
batch_number instead of a client-asserted batch_verified bool. Trusting
a client's own claim about whether its batch is genuine defeats the
whole point of the counterfeit-check trust feature (CLAUDE.md: "~25% of
India's agrochemical market is non-genuine... a fake product failing
would otherwise be recorded by M8 as a genuine product failing"). The
server verifies batch_number against M2's check_batch() itself.
"""
from typing import Optional

from pydantic import BaseModel


class OutcomeLogInput(BaseModel):
    farmer_id: str
    product_used: str
    batch_number: str
    application_date: str
    observed_outcome: Optional[str] = None
    yield_result: Optional[float] = None
    # Not part of CLAUDE.md's locked OutcomeLog output contract (added
    # only here, on the input), and not returned in the response either
    # — it's threaded into the internally persisted record so M9's
    # get_confidence_boost(product_name, district) has something real to
    # key against. Optional: a log without it just won't be district-
    # filterable later, not rejected.
    district: Optional[str] = None


class OutcomeLog(BaseModel):
    farmer_id: str
    product_used: str
    batch_verified: bool
    application_date: str
    observed_outcome: Optional[str] = None
    yield_result: Optional[float] = None
    synced: bool