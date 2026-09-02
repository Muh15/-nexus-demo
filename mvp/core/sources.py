from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceCapability:
    name: str
    kind: str
    readable: bool = True
    writable: bool = False
    notes: str = ""


DEFAULT_SOURCE_CATALOG: tuple[SourceCapability, ...] = (
    SourceCapability("business_files", "file", readable=True, notes="CSV, JSON, TXT, XLSX, PDF"),
    SourceCapability("email", "communication", readable=True, writable=True, notes="Future Gmail/Microsoft 365 adapter"),
    SourceCapability("erp", "business_system", readable=True, writable=True, notes="Future ERP adapters"),
    SourceCapability("crm", "business_system", readable=True, writable=True, notes="Future CRM adapters"),
    SourceCapability("approved_web", "external", readable=True, notes="Approved public or authorized sources"),
)


def available_sources() -> list[dict[str, object]]:
    """Expose a stable source catalog without coupling it to implementations."""
    return [
        {
            "name": source.name,
            "kind": source.kind,
            "readable": source.readable,
            "writable": source.writable,
            "notes": source.notes,
        }
        for source in DEFAULT_SOURCE_CATALOG
    ]
