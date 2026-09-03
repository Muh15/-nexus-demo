from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .base import ConnectorResult


@dataclass(frozen=True, slots=True)
class PaginationResult:
    records: list[dict[str, Any]]
    cursor: str | None
    pages: int


def fetch_all_pages(
    fetch_page: Callable[[str | None], ConnectorResult],
    *,
    initial_cursor: str | None = None,
    max_pages: int = 10,
) -> PaginationResult:
    """Fetch a bounded sequence of cursor pages without allowing runaway loops."""
    if max_pages <= 0:
        raise ValueError("max_pages must be positive")
    records: list[dict[str, Any]] = []
    cursor = initial_cursor
    seen: set[str] = set()
    pages = 0
    while pages < max_pages:
        if cursor is not None:
            if cursor in seen:
                raise ValueError("business API pagination cursor repeated")
            seen.add(cursor)
        result = fetch_page(cursor)
        records.extend(result.records)
        pages += 1
        next_cursor = result.metadata.get("next_cursor")
        if not isinstance(next_cursor, str) or not next_cursor:
            return PaginationResult(records, None, pages)
        cursor = next_cursor
    return PaginationResult(records, cursor, pages)
