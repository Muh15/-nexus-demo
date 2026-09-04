from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
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
    allow_private_ips: bool = False


class HttpJsonConnector(Connector):
    """Fetch JSON from an explicitly allow-listed HTTP(S) endpoint."""

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
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("URL must not contain credentials, query parameters, or fragments")
        if not parsed.hostname:
            raise ValueError("URL must include a hostname")
        host = parsed.hostname.lower().rstrip(".")
        allowed = {item.lower().rstrip(".") for item in self.config.allowed_hosts}
        if host not in allowed:
            raise ValueError("URL host is not allow-listed")
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal is not None:
            self._reject_unsafe_ip(literal)
            return
        if not self.config.allow_private_ips:
            try:
                addresses = {
                    ipaddress.ip_address(info[4][0])
                    for info in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
                }
            except socket.gaierror as exc:
                raise ValueError(f"unable to resolve URL host: {host}") from exc
            if not addresses:
                raise ValueError(f"URL host did not resolve: {host}")
            for address in addresses:
                self._reject_unsafe_ip(address)

    def _reject_unsafe_ip(self, address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
        if self.config.allow_private_ips:
            return
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        ):
            raise ValueError("URL host resolves to a non-public IP address")

    @staticmethod
    def _records(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list) and all(isinstance(item, dict) for item in data):
            return data
        raise ValueError("JSON must be an object or an array of objects")
