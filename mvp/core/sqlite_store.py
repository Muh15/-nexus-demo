from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any


class SQLiteMissionStore:
    """Durable mission store with an explicit tenant boundary."""

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
            connection.commit()

    def save(self, mission_id: str, payload: dict[str, Any], updated_at: str, tenant_id: str = DEFAULT_TENANT) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO missions (mission_id, tenant_id, payload, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(mission_id) DO UPDATE SET
                    tenant_id=excluded.tenant_id,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (mission_id, tenant_id, serialized, updated_at),
            )
            connection.commit()

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
