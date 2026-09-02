from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from .base import Connector, ConnectorResult


@dataclass(frozen=True, slots=True)
class BusinessApiConfig:
    name: str
    base_url: str
    allowed_hosts: frozenset[str]
    token_env: str | None = None
    timeout_seconds: float = 10.0
    max_response_bytes: int = 2_000_000
    cursor_param: str = "cursor"


class BusinessApiConnector(Connector):
    """Scoped REST connector for CRM/ERP/supplier-style business APIs."""

    def __init__(self, config: BusinessApiConfig) -> None:
        if not config.name.strip():
            raise ValueError("connector name is required")
        if config.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if config.max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        parsed = urlparse(config.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("base_url must be an http(s) URL with a hostname")
        host = parsed.hostname.lower().rstrip(".")
        allowed = {item.lower().rstrip(".") for item in config.allowed_hosts}
        if host not in allowed:
            raise ValueError("base_url host is not allow-listed")
        self.config = config
        self.name = config.name

    def ingest(self, payload: str, *, filename: str | None = None) -> ConnectorResult:
        del filename
        return self.fetch(payload)

    def fetch(self, endpoint: str = "", *, cursor: str | None = None) -> ConnectorResult:
        url = urljoin(self.config.base_url.rstrip("/") + "/", endpoint.lstrip("/"))
        self._validate_url(url)
        headers = {"Accept": "application/json"}
        if self.config.token_env:
            token = os.getenv(self.config.token_env, "").strip()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        params = {self.config.cursor_param: cursor} if cursor else None
        with httpx.Client(timeout=self.config.timeout_seconds, follow_redirects=False, headers=headers) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            raw = response.content
            content_type = response.headers.get("content-type", "")

        if len(raw) > self.config.max_response_bytes:
            raise ValueError("business API response exceeds configured size limit")
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise ValueError("business API response is not valid JSON") from exc

        records, next_cursor = self._records_and_cursor(data)
        digest = hashlib.sha256(raw).hexdigest()
        return ConnectorResult(
            source=self.name,
            records=records,
            metadata={
                "url": url,
                "status_code": response.status_code,
                "content_type": content_type,
                "record_count": len(records),
                "sha256": digest,
                "next_cursor": next_cursor,
                "credential_env": self.config.token_env,
            },
            provenance=[
                {
                    "source": self.name,
                    "url": url,
                    "status_code": response.status_code,
                    "sha256": digest,
                    "locator": f"item:{index}",
                }
                for index, _ in enumerate(records, start=1)
            ],
        )

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("only http and https URLs are allowed")
        host = parsed.hostname.lower().rstrip(".")
        allowed = {item.lower().rstrip(".") for item in self.config.allowed_hosts}
        if host not in allowed:
            raise ValueError("URL host is not allow-listed")

    @staticmethod
    def _records_and_cursor(data: Any) -> tuple[list[dict[str, Any]], str | None]:
        if isinstance(data, list) and all(isinstance(item, dict) for item in data):
            return data, None
        if not isinstance(data, dict):
            raise ValueError("business API JSON must be an object or an array of objects")
        candidate = data.get("records", data.get("items", data.get("data")))
        if candidate is None:
            return [data], data.get("next_cursor") if isinstance(data.get("next_cursor"), str) else None
        if not isinstance(candidate, list) or not all(isinstance(item, dict) for item in candidate):
            raise ValueError("business API record collection must contain objects")
        cursor = data.get("next_cursor") or data.get("nextCursor") or data.get("cursor")
        return candidate, cursor if isinstance(cursor, str) else None
