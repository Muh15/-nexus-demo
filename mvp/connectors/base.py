from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ConnectorResult:
    source: str
    records: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class Connector:
    """Minimal connector contract used by the NEXUS MVP."""

    name: str = "base"

    def ingest(self, payload: Any, *, filename: str | None = None) -> ConnectorResult:
        raise NotImplementedError
