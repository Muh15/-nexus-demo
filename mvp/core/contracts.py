from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class Evidence:
    id: str
    source: str
    title: str
    content: str
    locator: str | None = None
    confidence: int = 100
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Entity:
    id: str
    type: str
    name: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Relationship:
    subject_id: str
    predicate: str
    object_id: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BusinessContext:
    tenant_id: str
    entities: tuple[Entity, ...] = ()
    relationships: tuple[Relationship, ...] = ()
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True, slots=True)
class Goal:
    id: str
    tenant_id: str
    statement: str
    constraints: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Signal:
    id: str
    source: str
    title: str
    value: str
    impact: str
    confidence: int = 100
    evidence_ids: tuple[str, ...] = ()


class SourceConnector(Protocol):
    name: str

    def discover(self, goal: Goal, context: BusinessContext) -> list[Evidence]: ...


class ReasoningEngine(Protocol):
    def analyze(self, goal: Goal, context: BusinessContext, signals: list[Signal]) -> dict[str, Any]: ...


class ActionExecutor(Protocol):
    name: str

    def execute(self, action: dict[str, Any]) -> dict[str, Any]: ...


class Verifier(Protocol):
    name: str

    def verify(self, action: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]: ...
