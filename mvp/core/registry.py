from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ComponentRegistry:
    """Dependency registry that keeps implementations replaceable."""

    connectors: dict[str, Any]
    executors: dict[str, Any]
    verifiers: dict[str, Any]

    @classmethod
    def empty(cls) -> "ComponentRegistry":
        return cls(connectors={}, executors={}, verifiers={})

    def add_connector(self, name: str, connector: Any) -> None:
        if name in self.connectors:
            raise ValueError(f"connector already registered: {name}")
        self.connectors[name] = connector

    def add_executor(self, name: str, executor: Any) -> None:
        if name in self.executors:
            raise ValueError(f"executor already registered: {name}")
        self.executors[name] = executor

    def add_verifier(self, name: str, verifier: Any) -> None:
        if name in self.verifiers:
            raise ValueError(f"verifier already registered: {name}")
        self.verifiers[name] = verifier

    def describe(self) -> dict[str, list[str]]:
        return {
            "connectors": sorted(self.connectors),
            "executors": sorted(self.executors),
            "verifiers": sorted(self.verifiers),
        }
