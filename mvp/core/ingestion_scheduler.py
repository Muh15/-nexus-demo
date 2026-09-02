from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass(frozen=True, slots=True)
class IngestionJob:
    id: str
    tenant_id: str
    connector: str
    source: str
    interval_seconds: int
    enabled: bool
    cursor: str | None
    config: dict[str, Any]
    last_run_at: str | None
    next_run_at: str
    created_at: str
    updated_at: str


class SQLiteIngestionScheduler:
    """Durable scheduler metadata; execution remains connector-independent."""

    def __init__(self, path: str | Path = "nexus_mvp.sqlite3") -> None:
        self.path = str(path)
        self._lock = RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        if self.path not in {":memory:", ""}:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestion_jobs (
                    job_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    connector TEXT NOT NULL,
                    source TEXT NOT NULL,
                    interval_seconds INTEGER NOT NULL,
                    enabled INTEGER NOT NULL,
                    cursor TEXT,
                    config TEXT NOT NULL,
                    last_run_at TEXT,
                    next_run_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_due ON ingestion_jobs (tenant_id, enabled, next_run_at)")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestion_job_runs (
                    run_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    cursor_before TEXT,
                    cursor_after TEXT,
                    message TEXT NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_ingestion_runs_job ON ingestion_job_runs (tenant_id, job_id, started_at DESC)")
            connection.commit()

    def register(self, *, tenant_id: str, connector: str, source: str, interval_seconds: int, config: dict[str, Any] | None = None, cursor: str | None = None, start_at: datetime | None = None, job_id: str | None = None) -> IngestionJob:
        if not tenant_id or not connector or not source:
            raise ValueError("tenant_id, connector, and source are required")
        if interval_seconds < 60:
            raise ValueError("interval_seconds must be at least 60")
        now = utc_now()
        next_run = start_at or now
        job = IngestionJob(
            id=job_id or f"ING-{uuid4().hex[:12].upper()}", tenant_id=tenant_id, connector=connector, source=source,
            interval_seconds=interval_seconds, enabled=True, cursor=cursor, config=dict(config or {}),
            last_run_at=None, next_run_at=_iso(next_run), created_at=_iso(now), updated_at=_iso(now),
        )
        import json
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO ingestion_jobs (job_id, tenant_id, connector, source, interval_seconds, enabled, cursor, config, last_run_at, next_run_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (job.id, job.tenant_id, job.connector, job.source, job.interval_seconds, 1, job.cursor, json.dumps(job.config, ensure_ascii=False, separators=(",", ":")), job.last_run_at, job.next_run_at, job.created_at, job.updated_at),
            )
            connection.commit()
        return job

    def get_due(self, tenant_id: str, now: datetime | None = None) -> list[IngestionJob]:
        import json
        current = _iso(now or utc_now())
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT * FROM ingestion_jobs WHERE tenant_id = ? AND enabled = 1 AND next_run_at <= ? ORDER BY next_run_at ASC", (tenant_id, current)).fetchall()
        return [self._row(row, json) for row in rows]

    def list(self, tenant_id: str) -> list[IngestionJob]:
        import json
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT * FROM ingestion_jobs WHERE tenant_id = ? ORDER BY created_at ASC", (tenant_id,)).fetchall()
        return [self._row(row, json) for row in rows]

    def record_run(self, job_id: str, tenant_id: str, *, status: str, message: str, cursor_before: str | None, cursor_after: str | None, started_at: datetime | None = None, finished_at: datetime | None = None) -> str:
        run_id = f"RUN-{uuid4().hex[:12].upper()}"
        started = started_at or utc_now()
        finished = finished_at or utc_now()
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT interval_seconds FROM ingestion_jobs WHERE job_id = ? AND tenant_id = ?", (job_id, tenant_id)).fetchone()
            if row is None:
                raise KeyError("Ingestion job not found")
            next_run = finished + timedelta(seconds=int(row["interval_seconds"]))
            connection.execute(
                "INSERT INTO ingestion_job_runs (run_id, job_id, tenant_id, started_at, finished_at, status, cursor_before, cursor_after, message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, job_id, tenant_id, _iso(started), _iso(finished), status, cursor_before, cursor_after, message),
            )
            connection.execute("UPDATE ingestion_jobs SET cursor = ?, last_run_at = ?, next_run_at = ?, updated_at = ? WHERE job_id = ? AND tenant_id = ?", (cursor_after, _iso(finished), _iso(next_run), _iso(finished), job_id, tenant_id))
            connection.commit()
        return run_id

    def disable(self, job_id: str, tenant_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute("UPDATE ingestion_jobs SET enabled = 0, updated_at = ? WHERE job_id = ? AND tenant_id = ?", (_iso(utc_now()), job_id, tenant_id))
            connection.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _row(row: sqlite3.Row, json_module: Any) -> IngestionJob:
        return IngestionJob(
            id=row["job_id"], tenant_id=row["tenant_id"], connector=row["connector"], source=row["source"],
            interval_seconds=int(row["interval_seconds"]), enabled=bool(row["enabled"]), cursor=row["cursor"],
            config=dict(json_module.loads(row["config"])), last_run_at=row["last_run_at"], next_run_at=row["next_run_at"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
