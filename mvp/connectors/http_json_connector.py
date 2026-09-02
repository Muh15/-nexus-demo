from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from .base import Connector, ConnectorResult


@dataclass(frozen=True, slots=True)
class HttpJsonConfig:
    """Security limits for an authorized JSON HTTP source."""

    allowed_hosts: frozenset[str]
    timeout_seconds: float = 10.0
    max_response_bytes: int = 2_000_000
    follow_redirects: bool = False


class HttpJsonConnector(Connector):
    """Fetch JSON from an explicitly allow-listed HTTP(S) endpoint.

    Transport and validation live here; business reasoning stays in the core.
    Credentials, when needed, should be supplied by the caller/runtime rather
    than hard-coded into the connector.
    """

    name = "http_json"

    def __init__(self, config: HttpJsonConfig):
        if not config.allowed_hosts:
            raise ValueError("at least one allowed host is required")
        if config.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if config.max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        self.config = config

    def ingest(self, payload: str, *, filename: str | None = None) -> ConnectorResult:
        del filename
        return self.fetch(payload)

    def fetch(self, url: str, *, headers: dict[str, str] | None = None) -> ConnectorResult:
        self._validate_url(url)
        with httpx.Client(
            timeout=self.config.timeout_seconds,
            follow_redirects=self.config.follow_redirects,
            headers={"Accept": "application/json", **(headers or {})},
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            raw = response.content

        if len(raw) > self.config.max_response_bytes:
            raise ValueError("JSON response exceeds configured size limit")
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise ValueError("HTTP response is not valid JSON") from exc

        records = self._records(data)
        digest = hashlib.sha256(raw).hexdigest()
        return ConnectorResult(
            source=self.name,
            records=records,
            metadata={
                "url": url,
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "record_count": len(records),
                "sha256": digest,
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
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("only http and https URLs are allowed")
        if not parsed.hostname:
            raise ValueError("URL must include a hostname")
        host = parsed.hostname.lower().rstrip(".")
        allowed = {item.lower().rstrip(".") for item in self.config.allowed_hosts}
        if host not in allowed:
            raise ValueError("URL host is not allow-listed")

    @staticmethod
    def _records(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list) and all(isinstance(item, dict) for item in data):
            return data
        raise ValueError("JSON must be an object or an array of objects")
