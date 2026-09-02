from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class MemoryObservation:
    """A time-stamped fact with provenance, isolated by tenant."""

    id: str
    tenant_id: str
    key: str
    value: Any
    source: str = "unknown"
    observed_at: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.observed_at:
            self.observed_at = datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class TenantMemory:
    tenant_id: str
    facts: dict[str, MemoryObservation] = field(default_factory=dict)
    history: list[MemoryObservation] = field(default_factory=list)


class MemoryStore:
    """Replaceable persistence boundary for NEXUS business memory.

    The MVP keeps memory in process, but exposes temporal observations rather
    than only the latest value. A future PostgreSQL/event-store adapter can
    implement the same contract without changing reasoning or orchestration.
    """

    def __init__(self) -> None:
        self._tenants: dict[str, TenantMemory] = {}

    def get(self, tenant_id: str) -> TenantMemory:
        memory = self._tenants.get(tenant_id)
        if memory is None:
            memory = TenantMemory(tenant_id)
            self._tenants[tenant_id] = memory
        return memory

    def remember(
        self,
        tenant_id: str,
        key: str,
        value: Any,
        *,
        source: str = "unknown",
        evidence_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryObservation:
        observation = MemoryObservation(
            id=f"mem:{tenant_id}:{len(self.get(tenant_id).history) + 1}",
            tenant_id=tenant_id,
            key=key,
            value=value,
            source=source,
            evidence_ids=list(evidence_ids or []),
            metadata=dict(metadata or {}),
        )
        memory = self.get(tenant_id)
        memory.facts[key] = observation
        memory.history.append(observation)
        return observation

    def latest(self, tenant_id: str, key: str) -> MemoryObservation | None:
        return self.get(tenant_id).facts.get(key)

    def history(self, tenant_id: str, key: str | None = None) -> list[MemoryObservation]:
        rows = list(self.get(tenant_id).history)
        if key is not None:
            rows = [row for row in rows if row.key == key]
        return rows

    def snapshot(self, tenant_id: str) -> dict[str, Any]:
        memory = self.get(tenant_id)
        return {
            "tenant_id": tenant_id,
            "facts": {
                key: {
                    "id": value.id,
                    "value": value.value,
                    "source": value.source,
                    "observed_at": value.observed_at,
                    "evidence_ids": value.evidence_ids,
                    "metadata": value.metadata,
                }
                for key, value in memory.facts.items()
            },
            "history_count": len(memory.history),
        }
