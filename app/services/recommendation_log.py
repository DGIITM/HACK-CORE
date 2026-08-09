"""M6's data source: a minimal append-only log of what M4 recommended,
where, and with what confidence. M4 (recommend.py) didn't persist any
recommendation history before this — verified by reading recommend.py
directly rather than assuming — so this is a small addition to that
module's side effects (one call after building a result), not a
rewrite of its scoring/retrieval logic.

Real local SQLite persistence, consistent with M7's outcome_store.py —
append-only, no sync/offline semantics needed here since there's no
"pending write" concept for a log that's only ever read back locally.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "recommendation_log.sqlite3"


def _init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recommendation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            district TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def log_recommendation(district: str, product_name: str, confidence_score: float) -> None:
    """Append-only — called once per confident recommendation, never
    updates or deletes existing rows."""
    _init_db()
    row = {
        "product_name": product_name,
        "confidence_score": confidence_score,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO recommendation_log (district, payload) VALUES (?, ?)",
        (district, json.dumps(row)),
    )
    conn.commit()
    conn.close()


def get_recent_recommendations(district: str) -> List[Dict]:
    """All logged recommendation rows for a district, oldest first."""
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT payload FROM recommendation_log WHERE district = ? ORDER BY id", (district,)
    ).fetchall()
    conn.close()
    return [json.loads(r[0]) for r in rows]
