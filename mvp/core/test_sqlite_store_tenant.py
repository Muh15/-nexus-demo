from __future__ import annotations

from core.sqlite_store import SQLiteMissionStore


def test_sqlite_store_isolates_missions_by_tenant(tmp_path):
    store = SQLiteMissionStore(tmp_path / "missions.sqlite3")
    store.save("M-1", {"owner": "one"}, "2026-09-02T10:00:00Z", tenant_id="tenant-one")
    store.save("M-2", {"owner": "two"}, "2026-09-02T10:01:00Z", tenant_id="tenant-two")

    assert store.get("M-1", tenant_id="tenant-one") == {"owner": "one"}
    assert store.get("M-1", tenant_id="tenant-two") is None
    assert store.list_ids(tenant_id="tenant-one") == ["M-1"]
    assert store.list_ids(tenant_id="tenant-two") == ["M-2"]
    assert store.delete("M-1", tenant_id="tenant-two") is False
    assert store.delete("M-1", tenant_id="tenant-one") is True


def test_sqlite_store_remains_backward_compatible_with_default_tenant(tmp_path):
    store = SQLiteMissionStore(tmp_path / "missions.sqlite3")
    store.save("M-legacy", {"ok": True}, "2026-09-02T10:00:00Z")

    assert store.get("M-legacy") == {"ok": True}
    assert store.list_ids() == ["M-legacy"]
