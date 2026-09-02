from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .models import BusinessContext, Evidence, Relationship


@dataclass(frozen=True, slots=True)
class GraphNode:
    id: str
    kind: str
    label: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GraphEdge:
    source_id: str
    relation: str
    target_id: str
    confidence: int
    evidence_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class IntelligenceGraph:
    """Read-oriented graph projection over business context.

    The graph is a projection, not the system of record. That keeps graph
    technology replaceable while giving the reasoning layer a stable structure
    for traversing entities, relationships, and supporting evidence.
    """

    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)

    @classmethod
    def from_context(cls, context: BusinessContext) -> "IntelligenceGraph":
        graph = cls()
        for entity in context.entities.values():
            graph.nodes[entity.id] = GraphNode(
                id=entity.id,
                kind=entity.type,
                label=entity.name,
                attributes=dict(entity.attributes),
            )
        for relationship in context.relationships:
            graph.edges.append(cls._edge(relationship))
        return graph

    @staticmethod
    def _edge(relationship: Relationship) -> GraphEdge:
        return GraphEdge(
            source_id=relationship.source_id,
            relation=relationship.relation,
            target_id=relationship.target_id,
            confidence=relationship.confidence,
            evidence_ids=tuple(relationship.evidence_ids),
        )

    def neighbors(self, node_id: str, *, relation: str | None = None) -> list[GraphNode]:
        targets = {
            edge.target_id
            for edge in self.edges
            if edge.source_id == node_id and (relation is None or edge.relation == relation)
        }
        return [self.nodes[target] for target in sorted(targets) if target in self.nodes]

    def supporting_evidence(self, node_id: str, evidence: Iterable[Evidence]) -> list[Evidence]:
        evidence_by_id = {item.id: item for item in evidence}
        ids: set[str] = set()
        for edge in self.edges:
            if edge.source_id == node_id or edge.target_id == node_id:
                ids.update(edge.evidence_ids)
        return [evidence_by_id[item] for item in sorted(ids) if item in evidence_by_id]

    def snapshot(self) -> dict[str, Any]:
        return {
            "nodes": [
                {"id": node.id, "kind": node.kind, "label": node.label, "attributes": node.attributes}
                for node in self.nodes.values()
            ],
            "edges": [
                {
                    "source_id": edge.source_id,
                    "relation": edge.relation,
                    "target_id": edge.target_id,
                    "confidence": edge.confidence,
                    "evidence_ids": list(edge.evidence_ids),
                }
                for edge in self.edges
            ],
        }


__all__ = ["GraphNode", "GraphEdge", "IntelligenceGraph"]
