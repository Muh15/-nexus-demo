from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Evidence:
    """A claim with enough provenance to audit where it came from."""

    id: str
    source: str
    claim: str
    value: Any
    confidence: int = 0
    collected_at: str = field(default_factory=utc_now)
    locator: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Entity:
    """Canonical business entity used to connect signals across systems."""

    id: str
    type: str
    name: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Relationship:
    source_id: str
    relation: str
    target_id: str
    confidence: int = 100
    evidence_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BusinessContext:
    """Small graph-like context that can grow as more connectors are added."""

    entities: dict[str, Entity] = field(default_factory=dict)
    relationships: list[Relationship] = field(default_factory=list)
    evidence: dict[str, Evidence] = field(default_factory=dict)

    def add_entity(self, entity: Entity) -> None:
        self.entities[entity.id] = entity

    def add_evidence(self, evidence: Evidence) -> None:
        self.evidence[evidence.id] = evidence

    def link(self, relationship: Relationship) -> None:
        self.relationships.append(relationship)

    def snapshot(self) -> dict[str, Any]:
        return {
            "entities": [
                {"id": e.id, "type": e.type, "name": e.name, "attributes": e.attributes}
                for e in self.entities.values()
            ],
            "relationships": [
                {
                    "source_id": r.source_id,
                    "relation": r.relation,
                    "target_id": r.target_id,
                    "confidence": r.confidence,
                    "evidence_ids": r.evidence_ids,
                }
                for r in self.relationships
            ],
            "evidence": [
                {
                    "id": e.id,
                    "source": e.source,
                    "claim": e.claim,
                    "value": e.value,
                    "confidence": e.confidence,
                    "collected_at": e.collected_at,
                    "locator": e.locator,
                    "metadata": e.metadata,
                }
                for e in self.evidence.values()
            ],
        }
