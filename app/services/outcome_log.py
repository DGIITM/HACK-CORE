"""M7 Application & Logging — batch check, outcome logging, offline sync."""
from app.schemas.outcome_log import OutcomeLog, OutcomeLogInput


def log_outcome(payload: OutcomeLogInput) -> OutcomeLog:
    # STUB: real logic verifies the product batch against the counterfeit
    # registry, writes to Firestore with persistentLocalCache so it works
    # offline in the field, and marks synced=True once connectivity
    # returns and the write actually lands.
    return OutcomeLog(
        farmer_id=payload.farmer_id,
        product_used=payload.product_used,
        batch_verified=payload.batch_verified,
        application_date=payload.application_date,
        observed_outcome=payload.observed_outcome,
        yield_result=payload.yield_result,
        synced=True,
    )
