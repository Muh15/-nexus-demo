from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import Connector, ConnectorResult

try:
    import openpyxl
except ImportError:  # pragma: no cover - exercised by dependency installation in CI
    openpyxl = None

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


@dataclass(slots=True)
class IngestedRecord:
    source: str
    fields: dict[str, Any]
    row_number: int
    locator: str | None = None


class FileConnector(Connector):
    """Ingest common business exports while preserving source provenance."""

    name = "file"
    SUPPORTED = {
        ".csv": "csv",
        ".json": "json",
        ".txt": "text",
        ".xlsx": "xlsx",
        ".pdf": "pdf",
    }

    def ingest(self, payload: str | bytes, *, filename: str | None = None) -> ConnectorResult:
        if not filename:
            raise ValueError("filename is required")
        suffix = self._suffix(filename)
        kind = self.SUPPORTED.get(suffix)
        if not kind:
            raise ValueError(f"Unsupported file type: {suffix or 'unknown'}")

        raw = payload.encode("utf-8") if isinstance(payload, str) else payload
        digest = hashlib.sha256(raw).hexdigest()
        records = self._parse(raw, kind)

        provenance = [
            {
                "source": "file",
                "filename": filename,
                "sha256": digest,
                "locator": record.locator or f"row:{record.row_number}",
            }
            for record in records
        ]

        return ConnectorResult(
            source="file",
            records=[r.fields for r in records],
            metadata={
                "filename": filename,
                "format": kind,
                "record_count": len(records),
                "sha256": digest,
            },
            provenance=provenance,
        )

    def _parse(self, raw: bytes, kind: str) -> list[IngestedRecord]:
        if kind == "csv":
            return self._csv(raw.decode("utf-8-sig"))
        if kind == "json":
            return self._json(raw.decode("utf-8-sig"))
        if kind == "text":
            return self._text(raw.decode("utf-8-sig"))
        if kind == "xlsx":
            return self._xlsx(raw)
        if kind == "pdf":
            return self._pdf(raw)
        raise ValueError(f"Unsupported format: {kind}")

    @staticmethod
    def _suffix(filename: str) -> str:
        return Path(filename.lower().strip()).suffix

    @staticmethod
    def _csv(text: str) -> list[IngestedRecord]:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ValueError("CSV must contain a header row")
        return [
            IngestedRecord(
                "file",
                {str(k).strip(): str(v).strip() for k, v in row.items() if k is not None},
                i,
                f"row:{i}",
            )
            for i, row in enumerate(reader, start=2)
        ]

    @staticmethod
    def _json(text: str) -> list[IngestedRecord]:
        data = json.loads(text)
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise ValueError("JSON must be an object or an array of objects")
        return [IngestedRecord("file", item, i, f"item:{i}") for i, item in enumerate(data, start=1)]

    @staticmethod
    def _text(text: str) -> list[IngestedRecord]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return [IngestedRecord("file", {"text": line}, i, f"line:{i}") for i, line in enumerate(lines, start=1)]

    @staticmethod
    def _xlsx(raw: bytes) -> list[IngestedRecord]:
        if openpyxl is None:
            raise RuntimeError("XLSX support requires openpyxl")
        workbook = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        records: list[IngestedRecord] = []
        for sheet in workbook.worksheets:
            rows = sheet.iter_rows(values_only=True)
            try:
                headers = [str(value).strip() if value is not None else f"column_{i}" for i, value in enumerate(next(rows), start=1)]
            except StopIteration:
                continue
            for row_number, row in enumerate(rows, start=2):
                values = list(row)
                records.append(
                    IngestedRecord(
                        "file",
                        {headers[i]: values[i] if i < len(values) else None for i in range(len(headers))},
                        row_number,
                        f"sheet:{sheet.title}!row:{row_number}",
                    )
                )
        return records

    @staticmethod
    def _pdf(raw: bytes) -> list[IngestedRecord]:
        if PdfReader is None:
            raise RuntimeError("PDF support requires pypdf")
        reader = PdfReader(io.BytesIO(raw))
        records: list[IngestedRecord] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                records.append(IngestedRecord("file", {"text": text}, page_number, f"page:{page_number}"))
        return records
