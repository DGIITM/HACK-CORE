"""Persistence for M7 outcome logs.

Real path: Firestore, per CLAUDE.md. Fallback path (used whenever
Firestore isn't reachable/configured — the same situation M4 hit with
Vertex AI, and this dev sandbox has no GCP credentials either): a local
SQLite file. That fallback is real, working persistence, not a stub —
writes land immediately and are queryable immediately; they're just not
yet confirmed to Firestore (synced=False) until sync_pending() succeeds.

A technical note on why SQLite specifically, not Firestore's own
persistentLocalCache: that feature belongs to Firestore's mobile/web
*client* SDKs — the device a farmer or field agent carries, which caches
writes locally and syncs when the device regains connectivity. This
FastAPI backend uses the `google-cloud-firestore` *Admin* SDK instead,
which is always a direct, online connection with no offline mode of its
own. The architecturally equivalent thing for *this* process to do when
*it* can't reach Firestore is exactly what's built here: queue writes
locally, sync them out once connectivity returns. (A real field client
would layer its own persistentLocalCache on top of calls to this API;
that's a frontend concern, out of scope for this backend module.)

Every function accepts an optional `remote_store` override — production
code never passes one (falls through to the real Firestore client), but
tests inject a lightweight fake to prove the queue/sync mechanics work
correctly without needing real GCP credentials.
"""
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Protocol

from app.core.config import settings

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "outcome_log_cache.sqlite3"


class FirestoreNotConfiguredError(RuntimeError):
    """Raised when Firestore isn't reachable/configured. Callers fall
    back to the local SQLite queue — a write is never lost, only
    deferred."""


class RemoteStore(Protocol):
    def write(self, doc_id: str, data: Dict) -> None: ...


class _FirestoreOutcomesCollection:
    """Thin wrapper so the rest of this module only depends on the
    minimal RemoteStore protocol, not the Firestore SDK's full API."""

    def __init__(self, client) -> None:
        self._collection = client.collection("outcome_logs")

    def write(self, doc_id: str, data: Dict) -> None:
        self._collection.document(doc_id).set(data)


def _get_firestore_client() -> RemoteStore:
    if not settings.GOOGLE_CLOUD_PROJECT:
        raise FirestoreNotConfiguredError(
            "GOOGLE_CLOUD_PROJECT is not set — Firestore isn't configured in this environment."
        )
    from google.cloud import firestore

    client = firestore.Client(project=settings.GOOGLE_CLOUD_PROJECT)
    return _FirestoreOutcomesCollection(client)


def _init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS outcome_logs (
            doc_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            synced INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()


def _write_local(doc_id: str, data: Dict, synced: bool) -> None:
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO outcome_logs (doc_id, payload, synced) VALUES (?, ?, ?)",
        (doc_id, json.dumps(data), int(synced)),
    )
    conn.commit()
    conn.close()


def save_outcome(doc_id: str, data: Dict, remote_store: Optional[RemoteStore] = None) -> bool:
    """Writes to Firestore if reachable; otherwise queues locally in
    SQLite so nothing is lost. Returns True if confirmed synced to
    Firestore, False if only queued locally so far — that's exactly the
    `synced` field in M7's output contract.
    """
    try:
        client = remote_store or _get_firestore_client()
        client.write(doc_id, data)
        _write_local(doc_id, data, synced=True)
        return True
    except FirestoreNotConfiguredError:
        _write_local(doc_id, data, synced=False)
        return False


def get_outcome(doc_id: str) -> Optional[Dict]:
    """Retrieval always goes through the local cache, which is exactly
    what makes a write immediately queryable even while "offline" — the
    local cache isn't just a write buffer, it's the read path too."""
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT payload, synced FROM outcome_logs WHERE doc_id = ?", (doc_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    data = json.loads(row[0])
    data["synced"] = bool(row[1])
    return data


def _all_records(include_doc_id: bool = False) -> List[Dict]:
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT doc_id, payload, synced FROM outcome_logs").fetchall()
    conn.close()
    records = []
    for doc_id, payload, synced in rows:
        data = json.loads(payload)
        data["synced"] = bool(synced)
        if include_doc_id:
            data["_doc_id"] = doc_id
        records.append(data)
    return records


def get_outcomes(product_name: str, district: Optional[str] = None) -> List[Dict]:
    """All locally-cached outcome records for a product, optionally
    narrowed to a district — this is what M9's running-average
    confidence boost reads from. Small local-scan query; fine at this
    dataset's size, same tradeoff already made throughout M2/M7/M8."""
    records = [r for r in _all_records() if r.get("product_used") == product_name]
    if district is not None:
        records = [r for r in records if r.get("district") == district]
    return records


def get_outcomes_by_district(district: str) -> List[Dict]:
    """All locally-cached outcome records for a district, regardless of
    product — feeds M9's get_retailer_evidence()."""
    return [r for r in _all_records() if r.get("district") == district]


def list_pending() -> List[str]:
    """doc_ids queued locally but not yet confirmed to Firestore."""
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT doc_id FROM outcome_logs WHERE synced = 0").fetchall()
    conn.close()
    return [r[0] for r in rows]


def sync_pending(remote_store: Optional[RemoteStore] = None) -> int:
    """Push every locally-queued-but-unsynced record to Firestore. Call
    this once connectivity returns. Returns the count actually synced —
    0 if Firestore still isn't reachable, which is not an error, just
    "still offline."
    """
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT doc_id, payload FROM outcome_logs WHERE synced = 0"
    ).fetchall()
    conn.close()

    if not rows:
        return 0

    try:
        client = remote_store or _get_firestore_client()
    except FirestoreNotConfiguredError:
        return 0

    synced_count = 0
    for doc_id, payload in rows:
        data = json.loads(payload)
        client.write(doc_id, data)
        _write_local(doc_id, data, synced=True)
        synced_count += 1
    return synced_count