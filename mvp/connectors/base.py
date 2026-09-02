from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ConnectorResult:
    source: str
    records: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance: list[dict[str, Any]] = field(default_factory=list)


class Connector:
    """Common contract for every NEXUS data connector.

    A connector is responsible for transport/parsing only. It must not make
    business decisions; it returns normalized-enough records plus provenance
    so the intelligence layer can reason over evidence without losing origin.
    """

    name: str = "base"

    def ingest(self, payload: Any, *, filename: str | None = None) -> ConnectorResult:
        raise NotImplementedError
