from fastapi.testclient import TestClient

from main import app


def test_api_mission_lifecycle_uses_core_orchestrator():
    client = TestClient(app)
    response = client.post(
        "/api/missions",
        json={
            "goal": "Reduce operating cost by 10% within 90 days",
            "constraints": ["Do not change quality"],
        },
    )
    assert response.status_code == 201
    mission = response.json()
    mission_id = mission["id"]
    assert mission["status"] == "awaiting_approval"
    assert mission["decision"]["evidence_count"] > 0
    assert mission["research"]["completed"] > 0

    approved = client.post(f"/api/missions/{mission_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    executed = client.post(f"/api/missions/{mission_id}/execute")
    assert executed.status_code == 200
    executed_payload = executed.json()
    assert executed_payload["status"] == "executed"
    assert executed_payload["action"]["output"]["sent"] is False

    verified = client.post(f"/api/missions/{mission_id}/verify")
    assert verified.status_code == 200
    verified_payload = verified.json()
    assert verified_payload["status"] == "verified"
    assert verified_payload["verification"]["status"] == "verified"


def test_api_rejects_execution_before_approval():
    client = TestClient(app)
    response = client.post(
        "/api/missions",
        json={"goal": "Reduce operating cost by 10% within 90 days"},
    )
    mission_id = response.json()["id"]
    blocked = client.post(f"/api/missions/{mission_id}/execute")
    assert blocked.status_code == 409
