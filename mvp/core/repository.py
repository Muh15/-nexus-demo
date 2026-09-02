from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

from .orchestrator import MissionState

T = TypeVar("T")


@dataclass(slots=True)
class InMemoryMissionRepository:
    """Replaceable persistence boundary for missions."""

    items: dict[str, MissionState] = field(default_factory=dict)

    def save(self, mission: MissionState) -> MissionState:
        self.items[mission.id] = mission
        return mission

    def get(self, mission_id: str) -> MissionState | None:
        return self.items.get(mission_id)

    def list_by_tenant(self, tenant_id: str) -> list[MissionState]:
        return [item for item in self.items.values() if item.tenant_id == tenant_id]
