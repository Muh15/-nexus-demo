from fastapi.testclient import TestClient

import main
from core.mission_repository import SQLiteMissionRepository
from core.sqlite_store import SQLiteMissionStore


client = TestClient(main.app)


def _isolated_store(tmp_path, name):
    original_repo = main.MISSION_REPOSITORY
    original_ingested = main.INGESTED_DATA
    main.MISSION_REPOSITORY = SQLiteMissionRepository(SQLiteMissionStore(tmp_path / name))
    main.INGESTED_DATA = {}
    return original_repo, original_ingested


def _restore(original_repo, original_ingested):
    main.MISSION_REPOSITORY = original_repo
    main.INGESTED_DATA = original_ingested


def _create_mission(headers=None):
    response = client.post(
        "/api/missions",
        json={"goal": "Reduce operating cost by 10% within 90 days"},
        headers=headers or {},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_api_mission_persists_across_cache_reset(tmp_path):
    original_repo, original_ingested = _isolated_store(tmp_path, "api.sqlite3")
    try:
        response = client.post(
            "/api/missions",
            json={
                "goal": "Reduce operating cost by 10% within 90 days",
                "constraints": ["Do not change quality"],
            },
        )
        assert response.status_code == 201
        mission_id = response.json()["id"]
        assert response.json()["status"] == "awaiting_approval"
        assert response.json()["tenant_id"] == "demo-tenant"
        assert response.json()["decision"]["evidence_count"] > 0

        assert client.post(f"/api/missions/{mission_id}/approve").status_code == 200
        executed = client.post(f"/api/missions/{mission_id}/execute")
        assert executed.status_code == 200
        executed_payload = executed.json()
        assert executed_payload["status"] == "executed"
        executed_at = executed_payload["action"]["executed_at"]
        execution_id = executed_payload["action"]["execution_id"]
        assert executed_payload["action"]["output"]["sent"] is False

        verified = client.post(f"/api/missions/{mission_id}/verify")
        assert verified.status_code == 200
        verified_payload = verified.json()
        assert verified_payload["status"] == "verified"
        assert verified_payload["verification"]["status"] == "verified"
        assert verified_payload["verification"]["execution_id"] == execution_id

        main.INGESTED_DATA = {}
        loaded = client.get(f"/api/missions/{mission_id}")
        assert loaded.status_code == 200
        payload = loaded.json()
        assert payload["id"] == mission_id
        assert payload["status"] == "verified"
        assert payload["verification"]["status"] == "verified"
        assert payload["action"]["execution_id"] == execution_id
        assert payload["action"]["executed_at"] == executed_at
    finally:
        _restore(original_repo, original_ingested)


def test_api_rejects_execute_before_approval(tmp_path):
    original_repo, original_ingested = _isolated_store(tmp_path, "blocked.sqlite3")
    try:
        mission_id = _create_mission()
        blocked = client.post(f"/api/missions/{mission_id}/execute")
        assert blocked.status_code == 409
    finally:
        _restore(original_repo, original_ingested)


def test_api_execution_is_idempotent(tmp_path):
    original_repo, original_ingested = _isolated_store(tmp_path, "idempotent.sqlite3")
    try:
        mission_id = _create_mission()
        assert client.post(f"/api/missions/{mission_id}/approve").status_code == 200
        first = client.post(f"/api/missions/{mission_id}/execute")
        second = client.post(f"/api/missions/{mission_id}/execute")
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["action"]["execution_id"] == second.json()["action"]["execution_id"]
        assert first.json()["action"]["executed_at"] == second.json()["action"]["executed_at"]
    finally:
        _restore(original_repo, original_ingested)


def test_api_approval_and_verification_are_idempotent(tmp_path):
    original_repo, original_ingested = _isolated_store(tmp_path, "idempotent_verify.sqlite3")
    try:
        mission_id = _create_mission()
        assert client.post(f"/api/missions/{mission_id}/approve").status_code == 200
        assert client.post(f"/api/missions/{mission_id}/approve").status_code == 200
        assert client.post(f"/api/missions/{mission_id}/execute").status_code == 200
        first_verify = client.post(f"/api/missions/{mission_id}/verify")
        second_verify = client.post(f"/api/missions/{mission_id}/verify")
        assert first_verify.status_code == 200
        assert second_verify.status_code == 200
        assert first_verify.json()["verification"]["execution_id"] == second_verify.json()["verification"]["execution_id"]
        assert first_verify.json()["verification"]["verified_at"] == second_verify.json()["verification"]["verified_at"]
    finally:
        _restore(original_repo, original_ingested)


def test_api_rejects_verify_before_execute(tmp_path):
    original_repo, original_ingested = _isolated_store(tmp_path, "verify_blocked.sqlite3")
    try:
        mission_id = _create_mission()
        blocked = client.post(f"/api/missions/{mission_id}/verify")
        assert blocked.status_code == 409
    finally:
        _restore(original_repo, original_ingested)


def test_api_returns_404_for_unknown_mission(tmp_path):
    original_repo, original_ingested = _isolated_store(tmp_path, "missing.sqlite3")
    try:
        assert client.get("/api/missions/NXS-DOES-NOT-EXIST").status_code == 404
        assert client.post("/api/missions/NXS-DOES-NOT-EXIST/approve").status_code == 404
    finally:
        _restore(original_repo, original_ingested)


def test_api_rejects_invalid_file_ingestion(tmp_path):
    original_repo, original_ingested = _isolated_store(tmp_path, "ingest.sqlite3")
    try:
        response = client.post("/api/ingest/file", json={"filename": "broken.csv", "content": "this is not a valid table"})
        assert response.status_code == 400
    finally:
        _restore(original_repo, original_ingested)


def test_api_isolates_missions_between_tenants(tmp_path):
    original_repo, original_ingested = _isolated_store(tmp_path, "tenant.sqlite3")
    try:
        alpha = {"X-Tenant-ID": "tenant-alpha"}
        beta = {"X-Tenant-ID": "tenant-beta"}
        mission_id = _create_mission(alpha)
        assert client.get(f"/api/missions/{mission_id}", headers=alpha).status_code == 200
        assert client.get(f"/api/missions/{mission_id}", headers=beta).status_code == 404
        assert [item["id"] for item in client.get("/api/missions", headers=alpha).json()] == [mission_id]
        assert client.get("/api/missions", headers=beta).json() == []
    finally:
        _restore(original_repo, original_ingested)


def test_api_isolates_ingested_records_between_tenants(tmp_path):
    original_repo, original_ingested = _isolated_store(tmp_path, "ingest_tenant.sqlite3")
    try:
        alpha = {"X-Tenant-ID": "tenant-alpha", "X-Actor-Role": "operator"}
        beta = {"X-Tenant-ID": "tenant-beta", "X-Actor-Role": "operator"}
        payload = {"filename": "suppliers.csv", "content": "supplier,monthly_spend\nAlpha,1000\n"}
        response = client.post("/api/ingest/file", json=payload, headers=alpha)
        assert response.status_code == 200
        assert client.get("/api/ingest", headers=alpha).json()["count"] == 1
        assert client.get("/api/ingest", headers=beta).json()["count"] == 0
    finally:
        _restore(original_repo, original_ingested)


def test_api_rejects_invalid_tenant_id(tmp_path):
    original_repo, original_ingested = _isolated_store(tmp_path, "tenant_validation.sqlite3")
    try:
        response = client.get("/api/context", headers={"X-Tenant-ID": "bad tenant id", "X-Actor-Role": "viewer"})
        assert response.status_code == 400
    finally:
        _restore(original_repo, original_ingested)


def test_api_exposes_runtime_registry(tmp_path):
    original_repo, original_ingested = _isolated_store(tmp_path, "runtime.sqlite3")
    try:
        response = client.get("/api/runtime")
        assert response.status_code == 200
        registry = response.json()["registry"]
        assert "file" in registry["connectors"]
        assert "action" in registry["executors"]
        assert "action" in registry["verifiers"]
    finally:
        _restore(original_repo, original_ingested)


def test_api_enforces_approval_role(tmp_path):
    original_repo, original_ingested = _isolated_store(tmp_path, "roles_approval.sqlite3")
    try:
        mission_id = _create_mission({"X-Tenant-ID": "tenant-role", "X-Actor-Role": "operator"})
        viewer = client.post(f"/api/missions/{mission_id}/approve", headers={"X-Tenant-ID": "tenant-role", "X-Actor-Role": "viewer"})
        operator = client.post(f"/api/missions/{mission_id}/approve", headers={"X-Tenant-ID": "tenant-role", "X-Actor-Role": "operator"})
        approver = client.post(f"/api/missions/{mission_id}/approve", headers={"X-Tenant-ID": "tenant-role", "X-Actor-Role": "approver"})
        assert viewer.status_code == 403
        assert operator.status_code == 403
        assert approver.status_code == 200
    finally:
        _restore(original_repo, original_ingested)


def test_api_enforces_execution_role(tmp_path):
    original_repo, original_ingested = _isolated_store(tmp_path, "roles_execute.sqlite3")
    try:
        tenant = "tenant-execute"
        mission_id = _create_mission({"X-Tenant-ID": tenant, "X-Actor-Role": "operator"})
        assert client.post(f"/api/missions/{mission_id}/approve", headers={"X-Tenant-ID": tenant, "X-Actor-Role": "approver"}).status_code == 200
        blocked = client.post(f"/api/missions/{mission_id}/execute", headers={"X-Tenant-ID": tenant, "X-Actor-Role": "viewer"})
        executed = client.post(f"/api/missions/{mission_id}/execute", headers={"X-Tenant-ID": tenant, "X-Actor-Role": "operator"})
        assert blocked.status_code == 403
        assert executed.status_code == 200
    finally:
        _restore(original_repo, original_ingested)


def test_api_rejects_invalid_actor_role(tmp_path):
    original_repo, original_ingested = _isolated_store(tmp_path, "role_validation.sqlite3")
    try:
        response = client.get("/api/context", headers={"X-Actor-Role": "superuser"})
        assert response.status_code == 400
    finally:
        _restore(original_repo, original_ingested)
