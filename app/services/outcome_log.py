"""M7 Application & Logging — batch check, outcome logging, offline sync.

Batch verification is done server-side against M2's check_batch(), never
trusted from client input — see app/schemas/outcome_log.py's docstring
for why. An invalid/counterfeit batch doesn't get silently accepted as
genuine: the record is still logged (a farmer's real-world outcome is
worth keeping either way, and this is exactly the data the retailer
console's counterfeit_alerts feature needs), but batch_verified comes
back false so nothing downstream mistakes it for a verified-genuine
product outcome.

Persistence goes through outcome_store.py, which is real Firestore when
configured and a real local SQLite queue (not a stub) when it isn't —
see that module's docstring for the offline/sync design.
"""
import logging
import uuid

from app.schemas.outcome_log import OutcomeLog, OutcomeLogInput
from app.services import data_foundation, outcome_store

logger = logging.getLogger(__name__)


def log_outcome(payload: OutcomeLogInput) -> OutcomeLog:
    batch_check = data_foundation.check_batch(payload.batch_number)
    batch_verified = batch_check["valid"]
    if not batch_verified:
        logger.warning(
            "Outcome logged against an unverified/counterfeit batch: farmer_id=%s batch_number=%s",
            payload.farmer_id,
            payload.batch_number,
        )

    record = {
        "farmer_id": payload.farmer_id,
        "product_used": payload.product_used,
        "batch_verified": batch_verified,
        "application_date": payload.application_date,
        "observed_outcome": payload.observed_outcome,
        "yield_result": payload.yield_result,
        # Persisted for M9's get_confidence_boost()/get_outcomes_by_district()
        # to query — not part of OutcomeLog's own contract, so it's simply
        # dropped (pydantic ignores unknown keys) when building the response below.
        "district": payload.district,
    }

    doc_id = f"{payload.farmer_id}-{uuid.uuid4().hex[:8]}"
    synced = outcome_store.save_outcome(doc_id, record)

    return OutcomeLog(**record, synced=synced)
