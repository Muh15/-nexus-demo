from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any


class SQLiteMissionStore:
    """Small durable mission store behind a replaceable persistence boundary."""

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
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def save(self, mission_id: str, payload: dict[str, Any], updated_at: str) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO missions (mission_id, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(mission_id) DO UPDATE SET
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (mission_id, serialized, updated_at),
            )
            connection.commit()

    def get(self, mission_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM missions WHERE mission_id = ?",
                (mission_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload"])

    def list_ids(self) -> list[str]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT mission_id FROM missions ORDER BY updated_at DESC"
            ).fetchall()
        return [row["mission_id"] for row in rows]

    def delete(self, mission_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM missions WHERE mission_id = ?",
                (mission_id,),
            )
            connection.commit()
            return cursor.rowcount > 0
