from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Any

from .base import Connector, ConnectorResult


@dataclass(slots=True)
class IngestedRecord:
    source: str
    fields: dict[str, Any]
    row_number: int


class FileConnector(Connector):
    """Ingest CSV, JSON, and simple text-based business exports.

    XLSX/PDF support is intentionally optional and will be added as dedicated
    adapters once the core normalization contract is stable.
    """

    name = "file"

    SUPPORTED = {".csv": "csv", ".json": "json", ".txt": "text"}

    def ingest(self, payload: str | bytes, *, filename: str | None = None) -> ConnectorResult:
        if not filename:
            raise ValueError("filename is required")
        suffix = self._suffix(filename)
        kind = self.SUPPORTED.get(suffix)
        if not kind:
            raise ValueError(f"Unsupported file type: {suffix or 'unknown'}")

        text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload
        if kind == "csv":
            records = self._csv(text)
        elif kind == "json":
            records = self._json(text)
        else:
            records = self._text(text)

        return ConnectorResult(
            source="file",
            records=[r.fields for r in records],
            metadata={
                "filename": filename,
                "format": kind,
                "record_count": len(records),
            },
        )

    @staticmethod
    def _suffix(filename: str) -> str:
        filename = filename.lower().strip()
        dot = filename.rfind(".")
        return filename[dot:] if dot >= 0 else ""

    @staticmethod
    def _csv(text: str) -> list[IngestedRecord]:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ValueError("CSV must contain a header row")
        return [
            IngestedRecord("file", {str(k).strip(): str(v).strip() for k, v in row.items()}, i)
            for i, row in enumerate(reader, start=2)
        ]

    @staticmethod
    def _json(text: str) -> list[IngestedRecord]:
        data = json.loads(text)
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise ValueError("JSON must be an object or an array of objects")
        return [IngestedRecord("file", item, i) for i, item in enumerate(data, start=1)]

    @staticmethod
    def _text(text: str) -> list[IngestedRecord]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return [IngestedRecord("file", {"text": line}, i) for i, line in enumerate(lines, start=1)]
