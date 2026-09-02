from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .memory import MemoryStore


@dataclass(frozen=True, slots=True)
class Change:
    tenant_id: str
    key: str
    previous: Any
    current: Any
    changed: bool
    kind: str
    source: str
    explanation: str


def detect_change(
    memory: MemoryStore,
    tenant_id: str,
    key: str,
    current: Any,
    *,
    source: str = "unknown",
) -> Change:
    """Compare a new observation with the latest known tenant-scoped value."""
    previous_entry = memory.latest(tenant_id, key)
    previous = previous_entry.value if previous_entry else None
    changed = previous_entry is not None and previous != current

    if previous_entry is None:
        kind = "new"
        explanation = "No previous observation exists for this key."
    elif changed:
        kind = "updated"
        explanation = "The latest observation differs from NEXUS business memory."
    else:
        kind = "unchanged"
        explanation = "The latest observation matches the current remembered value."

    memory.remember(tenant_id, key, current, source=source)
    return Change(
        tenant_id=tenant_id,
        key=key,
        previous=previous,
        current=current,
        changed=changed,
        kind=kind,
        source=source,
        explanation=explanation,
    )


def detect_record_changes(
    memory: MemoryStore,
    tenant_id: str,
    records: list[dict[str, Any]],
    *,
    source: str = "unknown",
    identity_fields: tuple[str, ...] = ("supplier", "contract", "customer", "id"),
) -> list[Change]:
    """Detect field-level changes while keeping identity deterministic."""
    changes: list[Change] = []
    for index, record in enumerate(records, start=1):
        identity = next((str(record[field]) for field in identity_fields if field in record and record[field] not in (None, "")), f"record-{index}")
        for field, value in sorted(record.items(), key=lambda item: str(item[0])):
            key = f"record:{identity}:{field}"
            changes.append(detect_change(memory, tenant_id, key, value, source=source))
    return changes
