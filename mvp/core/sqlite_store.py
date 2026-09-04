from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any


class SQLiteMissionStore:
    """Durable mission store with tenant-scoped snapshots and append-only history."""

    DEFAULT_TENANT = "default"

    def __init__(self, path: str | Path = "nexus_mvp.sqlite3") -> None:
        self.path = str(path)
        self._lock = RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        path = Path(self.path)
        if self.path not in {":memory:", ""}:
            path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS missions (
                    mission_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL DEFAULT 'default',
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(missions)").fetchall()}
            if "tenant_id" not in columns:
                connection.execute("ALTER TABLE missions ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_missions_tenant_updated ON missions (tenant_id, updated_at DESC)")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS mission_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mission_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE,
                    event_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_mission_events_tenant_mission ON mission_events (tenant_id, mission_id, event_id)"
            )
            connection.commit()

    def save(self, mission_id: str, payload: dict[str, Any], updated_at: str, tenant_id: str = DEFAULT_TENANT) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        with self._lock, self._connect() as connection:
            existing = connection.execute(
                "SELECT tenant_id FROM missions WHERE mission_id = ?",
                (mission_id,),
            ).fetchone()
            if existing is not None and existing["tenant_id"] != tenant_id:
                raise ValueError("Mission tenant cannot be changed after creation.")
            connection.execute(
                """
                INSERT INTO missions (mission_id, tenant_id, payload, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(mission_id) DO UPDATE SET
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (mission_id, tenant_id, serialized, updated_at),
            )
            connection.commit()

    def append_event(
        self,
        *,
        mission_id: str,
        tenant_id: str,
        event: dict[str, Any],
        recorded_at: str,
    ) -> bool:
        """Append one immutable event; duplicate semantic events are ignored."""
        event_json = json.dumps(event, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)
        event_hash = hashlib.sha256(
            f"{tenant_id}\n{mission_id}\n{event_json}".encode("utf-8")
        ).hexdigest()
        with self._lock, self._connect() as connection:
            mission = connection.execute(
                "SELECT tenant_id FROM missions WHERE mission_id = ?",
                (mission_id,),
            ).fetchone()
            if mission is None:
                raise ValueError("Cannot append an event for an unknown mission.")
            if mission["tenant_id"] != tenant_id:
                raise ValueError("Mission event tenant does not match the mission tenant.")
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO mission_events
                    (mission_id, tenant_id, event_hash, event_json, recorded_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (mission_id, tenant_id, event_hash, event_json, recorded_at),
            )
            connection.commit()
            return cursor.rowcount > 0

    def list_events(self, mission_id: str, tenant_id: str = DEFAULT_TENANT) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_id, mission_id, tenant_id, event_json, recorded_at
                FROM mission_events
                WHERE mission_id = ? AND tenant_id = ?
                ORDER BY event_id ASC
                """,
                (mission_id, tenant_id),
            ).fetchall()
        events: list[dict[str, Any]] = []
        for row in rows:
            event = json.loads(row["event_json"])
            events.append(
                {
                    "event_id": row["event_id"],
                    "mission_id": row["mission_id"],
                    "tenant_id": row["tenant_id"],
                    "recorded_at": row["recorded_at"],
                    "event": event,
                }
            )
        return events

    def get(self, mission_id: str, tenant_id: str = DEFAULT_TENANT) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT payload FROM missions WHERE mission_id = ? AND tenant_id = ?", (mission_id, tenant_id)).fetchone()
        if row is None:
            return None
        return json.loads(row["payload"])

    def list_ids(self, tenant_id: str = DEFAULT_TENANT) -> list[str]:
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT mission_id FROM missions WHERE tenant_id = ? ORDER BY updated_at DESC", (tenant_id,)).fetchall()
        return [row["mission_id"] for row in rows]

    def delete(self, mission_id: str, tenant_id: str = DEFAULT_TENANT) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM missions WHERE mission_id = ? AND tenant_id = ?", (mission_id, tenant_id))
            connection.commit()
            return cursor.rowcount > 0
