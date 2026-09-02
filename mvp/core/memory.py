from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TenantMemory:
    tenant_id: str
    facts: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)


class MemoryStore:
    """Small persistence boundary for NEXUS business memory.

    The MVP uses process memory. The interface is intentionally isolated so a
    durable store can replace it later without changing the intelligence layer.
    """

    def __init__(self) -> None:
        self._tenants: dict[str, TenantMemory] = defaultdict(lambda: TenantMemory(""))

    def get(self, tenant_id: str) -> TenantMemory:
        memory = self._tenants[tenant_id]
        if not memory.tenant_id:
            memory.tenant_id = tenant_id
        return memory

    def remember(self, tenant_id: str, key: str, value: Any, *, source: str = "unknown") -> None:
        memory = self.get(tenant_id)
        memory.facts[key] = value
        memory.history.append({"key": key, "value": value, "source": source})

    def snapshot(self, tenant_id: str) -> dict[str, Any]:
        memory = self.get(tenant_id)
        return {
            "tenant_id": memory.tenant_id,
            "facts": dict(memory.facts),
            "history_count": len(memory.history),
        }
