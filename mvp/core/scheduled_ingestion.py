from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from connectors.base import Connector, ConnectorResult

from .ingestion_scheduler import IngestionJob, SQLiteIngestionScheduler


@dataclass(frozen=True, slots=True)
class ScheduledIngestionResult:
    job_id: str
    run_id: str | None
    status: str
    records: int
    cursor_before: str | None
    cursor_after: str | None
    message: str


ConnectorFetcher = Callable[[Connector, IngestionJob], ConnectorResult]


def _default_fetch(connector: Connector, job: IngestionJob) -> ConnectorResult:
    endpoint = str(job.config.get("endpoint", ""))
    cursor = job.cursor
    fetch = getattr(connector, "fetch", None)
    if not callable(fetch):
        raise TypeError(f"connector {job.connector!r} does not expose fetch()")
    if cursor is None:
        return fetch(endpoint)
    try:
        return fetch(endpoint, cursor=cursor)
    except TypeError:
        return fetch(endpoint)


def _next_cursor(result: ConnectorResult) -> str | None:
    value = result.metadata.get("next_cursor")
    return value if isinstance(value, str) and value else None


class ScheduledIngestionExecutor:
    """Runs due durable ingestion jobs and advances pagination cursors atomically."""

    def __init__(
        self,
        scheduler: SQLiteIngestionScheduler,
        connectors: dict[str, Connector],
        fetcher: ConnectorFetcher | None = None,
    ) -> None:
        self.scheduler = scheduler
        self.connectors = dict(connectors)
        self.fetcher = fetcher or _default_fetch

    def run_due(self, tenant_id: str, *, now: datetime | None = None) -> list[ScheduledIngestionResult]:
        return [self.run_job(job, now=now) for job in self.scheduler.get_due(tenant_id, now=now)]

    def run_job(self, job: IngestionJob, *, now: datetime | None = None) -> ScheduledIngestionResult:
        connector = self.connectors.get(job.connector)
        started = now or datetime.now(timezone.utc)
        if connector is None:
            message = f"Connector {job.connector!r} is not registered."
            run_id = self.scheduler.record_run(
                job.id,
                job.tenant_id,
                status="unavailable",
                message=message,
                cursor_before=job.cursor,
                cursor_after=job.cursor,
                started_at=started,
                finished_at=started,
            )
            return ScheduledIngestionResult(job.id, run_id, "unavailable", 0, job.cursor, job.cursor, message)

        try:
            result = self.fetcher(connector, job)
            cursor_after = _next_cursor(result) or job.cursor
            records = len(result.records)
            message = json.dumps(
                {
                    "source": result.source,
                    "records": records,
                    "next_cursor": _next_cursor(result),
                    "sha256": result.metadata.get("sha256"),
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            # Use the scheduler's supplied clock so externally triggered/test runs
            # advance relative to the requested execution time, not wall-clock time.
            finished = started
            run_id = self.scheduler.record_run(
                job.id,
                job.tenant_id,
                status="completed",
                message=message,
                cursor_before=job.cursor,
                cursor_after=cursor_after,
                started_at=started,
                finished_at=finished,
            )
            return ScheduledIngestionResult(job.id, run_id, "completed", records, job.cursor, cursor_after, message)
        except Exception as exc:
            # Do not persist exception payloads; the type is enough for audit/debug.
            finished = started
            message = f"Scheduled ingestion failed: {type(exc).__name__}"
            run_id = self.scheduler.record_run(
                job.id,
                job.tenant_id,
                status="failed",
                message=message,
                cursor_before=job.cursor,
                cursor_after=job.cursor,
                started_at=started,
                finished_at=finished,
            )
            return ScheduledIngestionResult(job.id, run_id, "failed", 0, job.cursor, job.cursor, message)
