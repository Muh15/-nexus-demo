from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .orchestrator import MissionState, mission_from_snapshot
from .sqlite_store import SQLiteMissionStore


@dataclass(slots=True)
class SQLiteMissionRepository:
    """Persistence boundary for native MissionState snapshots."""

    store: SQLiteMissionStore

    def save(self, mission: MissionState, *, updated_at: str) -> MissionState:
        self.store.save(
            mission.id,
            mission.snapshot(),
            updated_at,
            tenant_id=mission.tenant_id,
        )
        return mission

    def get(self, tenant_id: str, mission_id: str) -> MissionState | None:
        payload = self.store.get(mission_id, tenant_id=tenant_id)
        if payload is None:
            return None
        mission = mission_from_snapshot(payload)
        if mission.tenant_id != tenant_id:
            return None
        return mission

    def list_by_tenant(self, tenant_id: str) -> list[MissionState]:
        missions: list[MissionState] = []
        for mission_id in self.store.list_ids(tenant_id=tenant_id):
            mission = self.get(tenant_id, mission_id)
            if mission is not None:
                missions.append(mission)
        return missions

    def delete(self, tenant_id: str, mission_id: str) -> bool:
        return self.store.delete(mission_id, tenant_id=tenant_id)
