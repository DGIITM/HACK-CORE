"""M7: batch verification (server-side, never client-trusted) and the
offline-write / reconnect-and-sync claim for outcome_store.py.

Every test gets an isolated SQLite file (via the `isolated_store`
fixture) so runs don't accumulate state in the repo's real
data/outcome_log_cache.sqlite3 or interfere with each other.
"""
import pytest

from app.schemas.outcome_log import OutcomeLogInput
from app.services import outcome_log, outcome_store


class FakeRemote:
    """Stands in for a configured Firestore client — proves the
    save/sync logic is correct without needing real GCP credentials,
    which this dev sandbox doesn't have (same situation M4 hit with
    Vertex AI)."""

    def __init__(self):
        self.written = {}

    def write(self, doc_id, data):
        self.written[doc_id] = dict(data)


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(outcome_store, "DB_PATH", tmp_path / "outcome_log_cache.sqlite3")
    return outcome_store


# --- The offline / reconnect claim ------------------------------------------

def test_write_while_disconnected_is_retrievable_before_sync(isolated_store):
    """Simulates "disconnected": no remote_store is passed, and this dev
    sandbox genuinely has no GOOGLE_CLOUD_PROJECT configured, so
    save_outcome falls back to the local queue exactly like it would in
    the field with no signal."""
    synced = isolated_store.save_outcome("doc-1", {"farmer_id": "f-1", "yield_result": 40.0})

    assert synced is False
    record = isolated_store.get_outcome("doc-1")
    assert record is not None
    assert record["farmer_id"] == "f-1"
    assert record["synced"] is False
    assert "doc-1" in isolated_store.list_pending()


def test_reconnecting_syncs_queued_writes_and_flips_synced_true(isolated_store):
    isolated_store.save_outcome("doc-2", {"farmer_id": "f-2", "yield_result": 38.0})
    assert isolated_store.get_outcome("doc-2")["synced"] is False

    fake_remote = FakeRemote()
    synced_count = isolated_store.sync_pending(remote_store=fake_remote)

    assert synced_count == 1
    assert "doc-2" in fake_remote.written
    assert fake_remote.written["doc-2"]["farmer_id"] == "f-2"

    # retrievable, and now shows synced, once "reconnected"
    record = isolated_store.get_outcome("doc-2")
    assert record["synced"] is True
    assert "doc-2" not in isolated_store.list_pending()


def test_sync_pending_is_a_no_op_when_still_offline(isolated_store):
    isolated_store.save_outcome("doc-3", {"farmer_id": "f-3", "yield_result": 41.0})
    synced_count = isolated_store.sync_pending()  # no remote_store, still genuinely offline here
    assert synced_count == 0
    assert isolated_store.get_outcome("doc-3")["synced"] is False
    assert "doc-3" in isolated_store.list_pending()


def test_save_outcome_with_a_reachable_remote_syncs_immediately(isolated_store):
    fake_remote = FakeRemote()
    synced = isolated_store.save_outcome("doc-4", {"farmer_id": "f-4"}, remote_store=fake_remote)
    assert synced is True
    assert "doc-4" in fake_remote.written
    assert isolated_store.get_outcome("doc-4")["synced"] is True
    assert isolated_store.list_pending() == []


def test_get_outcome_returns_none_for_unknown_doc(isolated_store):
    assert isolated_store.get_outcome("does-not-exist") is None


def test_multiple_writes_for_the_same_farmer_do_not_collide(isolated_store):
    isolated_store.save_outcome("doc-a", {"farmer_id": "f-5", "yield_result": 10.0})
    isolated_store.save_outcome("doc-b", {"farmer_id": "f-5", "yield_result": 20.0})
    assert isolated_store.get_outcome("doc-a")["yield_result"] == 10.0
    assert isolated_store.get_outcome("doc-b")["yield_result"] == 20.0


# --- Batch verification (server-side, never client-trusted) ----------------

def test_log_outcome_verifies_a_genuine_batch(isolated_store):
    result = outcome_log.log_outcome(
        OutcomeLogInput(
            farmer_id="farmer-batch-ok",
            product_used="Trichoderma viride bio-fungicide",
            batch_number="TRV-2026-00417",
            application_date="2026-03-14",
            observed_outcome="greener leaves after 3 weeks",
            yield_result=42.5,
        )
    )
    assert result.batch_verified is True


def test_log_outcome_flags_an_unknown_batch_rather_than_accepting_it(isolated_store):
    """This is the core of the constraint: a made-up/counterfeit batch
    number must never silently come back verified=True."""
    result = outcome_log.log_outcome(
        OutcomeLogInput(
            farmer_id="farmer-batch-bad",
            product_used="Trichoderma viride bio-fungicide",
            batch_number="TOTALLY-FAKE-BATCH-0000",
            application_date="2026-03-14",
            observed_outcome="no visible change",
            yield_result=30.0,
        )
    )
    assert result.batch_verified is False


def test_log_outcome_still_persists_records_with_unverified_batches(isolated_store):
    """An invalid batch is reported honestly, not silently swapped to
    True — but the outcome itself is still logged (real data worth
    keeping for the counterfeit-alert trust feature), not discarded."""
    result = outcome_log.log_outcome(
        OutcomeLogInput(
            farmer_id="farmer-batch-bad-2",
            product_used="Trichoderma viride bio-fungicide",
            batch_number="ANOTHER-FAKE-BATCH",
            application_date="2026-03-14",
            observed_outcome="no visible change",
            yield_result=29.0,
        )
    )
    assert result.batch_verified is False
    assert result.farmer_id == "farmer-batch-bad-2"
    assert result.observed_outcome == "no visible change"


def test_log_outcome_returns_exact_contract_shape(isolated_store):
    result = outcome_log.log_outcome(
        OutcomeLogInput(
            farmer_id="farmer-shape",
            product_used="Trichoderma viride bio-fungicide",
            batch_number="TRV-2026-00417",
            application_date="2026-03-14",
            observed_outcome="greener leaves",
            yield_result=42.5,
        )
    )
    for field in [
        "farmer_id", "product_used", "batch_verified",
        "application_date", "observed_outcome", "yield_result", "synced",
    ]:
        assert hasattr(result, field)
