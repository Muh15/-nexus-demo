from datetime import datetime, timedelta, timezone

from connectors.base import Connector, ConnectorResult
from core.ingestion_scheduler import SQLiteIngestionScheduler
from core.scheduled_ingestion import ScheduledIngestionExecutor


class CursorConnector(Connector):
    name = "cursor"

    def __init__(self):
        self.calls = []

    def fetch(self, endpoint="", *, cursor=None):
        self.calls.append(cursor)
        if cursor is None:
            return ConnectorResult(
                source=self.name,
                records=[{"id": 1}],
                metadata={"next_cursor": "page-2", "sha256": "a"},
            )
        return ConnectorResult(
            source=self.name,
            records=[{"id": 2}],
            metadata={"next_cursor": None, "sha256": "b"},
        )


def test_due_job_advances_cursor_and_records_run(tmp_path):
    scheduler = SQLiteIngestionScheduler(tmp_path / "jobs.sqlite3")
    connector = CursorConnector()
    executor = ScheduledIngestionExecutor(scheduler, {"cursor": connector})
    start = datetime(2026, 9, 3, 5, 0, tzinfo=timezone.utc)
    job = scheduler.register(
        tenant_id="tenant-a",
        connector="cursor",
        source="suppliers",
        interval_seconds=3600,
        config={"endpoint": "/items"},
        start_at=start,
    )

    first = executor.run_due("tenant-a", now=start + timedelta(minutes=1))
    assert len(first) == 1
    assert first[0].status == "completed"
    assert first[0].records == 1
    assert first[0].cursor_after == "page-2"
    assert connector.calls == [None]

    next_due = scheduler.get_due("tenant-a", now=start + timedelta(minutes=1))
    assert next_due == []

    second = executor.run_due("tenant-a", now=start + timedelta(hours=1, minutes=1))
    assert len(second) == 1
    assert second[0].status == "completed"
    assert second[0].cursor_before == "page-2"
    assert second[0].cursor_after == "page-2"
    assert connector.calls == [None, "page-2"]


def test_failed_job_preserves_cursor(tmp_path):
    scheduler = SQLiteIngestionScheduler(tmp_path / "failed.sqlite3")

    class Broken(Connector):
        name = "broken"

        def fetch(self, endpoint="", *, cursor=None):
            raise RuntimeError("boom")

    job = scheduler.register(
        tenant_id="tenant-a",
        connector="broken",
        source="erp",
        interval_seconds=60,
        cursor="page-7",
    )
    result = ScheduledIngestionExecutor(scheduler, {"broken": Broken()}).run_job(job)
    assert result.status == "failed"
    assert result.cursor_before == "page-7"
    assert result.cursor_after == "page-7"
    assert scheduler.list("tenant-a")[0].cursor == "page-7"


def test_missing_connector_is_recorded(tmp_path):
    scheduler = SQLiteIngestionScheduler(tmp_path / "missing.sqlite3")
    job = scheduler.register(
        tenant_id="tenant-a",
        connector="missing",
        source="crm",
        interval_seconds=60,
    )
    result = ScheduledIngestionExecutor(scheduler, {}).run_job(job)
    assert result.status == "unavailable"
    assert result.run_id
