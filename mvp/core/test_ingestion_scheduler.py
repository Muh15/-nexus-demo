from datetime import timedelta

import pytest

from core.ingestion_scheduler import SQLiteIngestionScheduler, utc_now


def test_job_lifecycle_persists_schedule_and_cursor(tmp_path):
    store = SQLiteIngestionScheduler(tmp_path / "ingestion.sqlite3")
    job = store.register(
        tenant_id="tenant-a",
        connector="crm",
        source="crm-primary",
        interval_seconds=300,
        config={"account": "acme"},
        cursor="0",
    )

    assert job.enabled is True
    assert job.cursor == "0"
    assert store.list("tenant-a")[0].config == {"account": "acme"}

    run_id = store.record_run(
        job.id,
        "tenant-a",
        status="completed",
        message="incremental sync complete",
        cursor_before="0",
        cursor_after="42",
    )
    assert run_id.startswith("RUN-")

    reopened = SQLiteIngestionScheduler(tmp_path / "ingestion.sqlite3")
    saved = reopened.list("tenant-a")[0]
    assert saved.last_run_at is not None
    assert saved.cursor == "42"
    assert reopened.get_due("tenant-a") == []
    assert saved.next_run_at > saved.last_run_at


def test_due_jobs_and_disable_are_tenant_scoped(tmp_path):
    store = SQLiteIngestionScheduler(tmp_path / "ingestion.sqlite3")
    due = utc_now()
    job_a = store.register(tenant_id="tenant-a", connector="erp", source="erp-a", interval_seconds=60, start_at=due)
    job_b = store.register(tenant_id="tenant-b", connector="erp", source="erp-b", interval_seconds=60, start_at=due)

    assert [item.id for item in store.get_due("tenant-a")] == [job_a.id]
    assert [item.id for item in store.get_due("tenant-b")] == [job_b.id]

    assert store.disable(job_a.id, "tenant-a") is True
    assert store.get_due("tenant-a") == []
    assert store.get_due("tenant-b")[0].id == job_b.id
    assert store.disable(job_a.id, "tenant-b") is False


def test_interval_must_be_at_least_one_minute(tmp_path):
    store = SQLiteIngestionScheduler(tmp_path / "ingestion.sqlite3")
    with pytest.raises(ValueError, match="at least 60"):
        store.register(tenant_id="tenant-a", connector="crm", source="crm", interval_seconds=30)
