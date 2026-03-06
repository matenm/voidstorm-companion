from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import TYPE_CHECKING

from voidstorm_companion.api_client import AuthError
from .config import CONFIG_DIR

if TYPE_CHECKING:
    from voidstorm_companion.api_client import ApiClient

_DB_PATH = Path(CONFIG_DIR) / "upload_queue.db"
_OLD_DB_PATH = Path.home() / ".voidstorm" / "upload_queue.db"
_MAX_ATTEMPTS = 5


def _migrate_queue_db():
    if _OLD_DB_PATH.exists() and not _DB_PATH.exists():
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _OLD_DB_PATH.rename(_DB_PATH)


def _connect(db_path: Path) -> sqlite3.Connection:
    _migrate_queue_db()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS upload_queue (
            id         INTEGER PRIMARY KEY,
            payload    TEXT    NOT NULL,
            created_at REAL    NOT NULL,
            attempts   INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()
    return conn


class UploadQueue:
    """Persistent SQLite-backed queue for failed upload payloads."""

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self._db_path = db_path
        self._conn = _connect(db_path)

    def enqueue(self, payload: dict) -> None:
        """Store a failed upload payload for later retry."""
        self._conn.execute(
            "INSERT INTO upload_queue (payload, created_at) VALUES (?, ?)",
            (json.dumps(payload), time.time()),
        )
        self._conn.commit()

    def pending_count(self) -> int:
        """Return the number of payloads currently in the queue."""
        row = self._conn.execute("SELECT COUNT(*) FROM upload_queue").fetchone()
        return row[0] if row else 0

    def flush(self, client: ApiClient) -> None:
        """Attempt to send all queued payloads, stopping on the first failure."""
        rows = self._conn.execute(
            "SELECT id, payload, attempts FROM upload_queue ORDER BY created_at ASC"
        ).fetchall()

        for row_id, raw_payload, attempts in rows:
            payload = json.loads(raw_payload)
            try:
                client.upload(
                    payload.get("sessions", []),
                    player_stats=payload.get("playerStats"),
                    tournaments=payload.get("tournaments"),
                    achievements=payload.get("achievements"),
                    leagues=payload.get("leagues"),
                    challenges=payload.get("challenges"),
                    audit_log=payload.get("auditLog"),
                )
                self._conn.execute("DELETE FROM upload_queue WHERE id = ?", (row_id,))
                self._conn.commit()
            except AuthError:
                raise
            except Exception:
                new_attempts = attempts + 1
                if new_attempts >= _MAX_ATTEMPTS:
                    self._conn.execute("DELETE FROM upload_queue WHERE id = ?", (row_id,))
                else:
                    self._conn.execute(
                        "UPDATE upload_queue SET attempts = ? WHERE id = ?",
                        (new_attempts, row_id),
                    )
                self._conn.commit()
                break
