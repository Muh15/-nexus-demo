from fastapi.testclient import TestClient

import main
from core.sqlite_store import SQLiteMissionStore


client = TestClient(main.app)


def test_api_mission_persists_across_cache_reset(tmp_path):
    original_store = main.MISSION_STORE
    original_cache = main.MISSIONS
    main.MISSION_STORE = SQLiteMissionStore(tmp_path / "api.sqlite3")
    main.MISSIONS = {}
    try:
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

        assert client.post(f"/api/missions/{mission_id}/approve").status_code == 200
        assert client.post(f"/api/missions/{mission_id}/execute").status_code == 200
        verified = client.post(f"/api/missions/{mission_id}/verify")
        assert verified.status_code == 200
        assert verified.json()["status"] == "verified"

        main.MISSIONS = {}
        loaded = client.get(f"/api/missions/{mission_id}")
        assert loaded.status_code == 200
        payload = loaded.json()
        assert payload["id"] == mission_id
        assert payload["status"] == "verified"
        assert payload["verification"]["status"] == "verified"
    finally:
        main.MISSION_STORE = original_store
        main.MISSIONS = original_cache
