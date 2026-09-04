from __future__ import annotations

import hashlib
import json
import os
import random
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx


@dataclass(frozen=True, slots=True)
class BusinessActionConfig:
    name: str
    base_url: str
    allowed_hosts: frozenset[str]
    token_env: str | None = None
    timeout_seconds: float = 10
    max_response_bytes: int = 2_000_000
    max_request_bytes: int = 200_000
    max_retries: int = 2
    retry_backoff_seconds: float = 0.05
    retry_backoff_max_seconds: float = 2.0
    retry_jitter_ratio: float = 0.25


class BusinessActionConnector:
    """Scoped write transport for explicitly configured business APIs."""

    def __init__(self, config: BusinessActionConfig) -> None:
        self.config = config
        parsed = urlparse(config.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("base_url must be an http(s) URL")
        if parsed.hostname not in config.allowed_hosts:
            raise ValueError(f"base_url host is not allow-listed: {parsed.hostname}")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("base_url must not contain credentials, query parameters, or fragments")
        if config.max_request_bytes <= 0 or config.max_response_bytes <= 0:
            raise ValueError("request/response limits must be positive")
        if config.max_retries < 0 or config.retry_backoff_seconds < 0:
            raise ValueError("retry settings must be non-negative")
        if config.retry_backoff_max_seconds <= 0 or config.retry_jitter_ratio < 0:
            raise ValueError("retry backoff/jitter settings are invalid")

    def _url(self, endpoint: str) -> str:
        url = urljoin(self.config.base_url.rstrip("/") + "/", endpoint.lstrip("/"))
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in self.config.allowed_hosts:
            raise ValueError(f"action host is not allow-listed: {parsed.hostname}")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("action URL must not contain credentials, query parameters, or fragments")
        return url

    def _retry_delay(self, attempt: int, response: httpx.Response | None = None) -> float:
        base = min(self.config.retry_backoff_seconds * (2**attempt), self.config.retry_backoff_max_seconds)
        jitter = base * self.config.retry_jitter_ratio * random.random()
        retry_after = 0.0
        if response is not None:
            value = response.headers.get("Retry-After", "").strip()
            if value.isdigit():
                retry_after = min(float(value), self.config.retry_backoff_max_seconds)
        return min(max(base + jitter, retry_after), self.config.retry_backoff_max_seconds)

    def _sleep_before_retry(self, attempt: int, response: httpx.Response | None = None) -> None:
        delay = self._retry_delay(attempt, response)
        if delay > 0:
            time.sleep(delay)

    def execute(self, method: str, endpoint: str, payload: dict, execution_id: str) -> dict:
        method = method.upper()
        if method not in {"POST", "PATCH"}:
            raise ValueError("only POST and PATCH actions are supported")
        if not execution_id or len(execution_id) > 128:
            raise ValueError("execution_id is required and must be <= 128 characters")
        if not isinstance(payload, dict):
            raise ValueError("action payload must be an object")

        url = self._url(endpoint)
        raw_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(raw_payload) > self.config.max_request_bytes:
            raise ValueError("request exceeds configured maximum size")

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Idempotency-Key": execution_id,
        }
        if self.config.token_env:
            token = os.getenv(self.config.token_env)
            if token:
                headers["Authorization"] = f"Bearer {token}"

        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                with httpx.Client(timeout=self.config.timeout_seconds, follow_redirects=False) as client:
                    response = client.request(method, url, headers=headers, content=raw_payload)
                transient = response.status_code in {408, 429} or 500 <= response.status_code < 600
                if transient and attempt < self.config.max_retries:
                    self._sleep_before_retry(attempt, response)
                    continue
                raw = response.content
                if len(raw) > self.config.max_response_bytes:
                    raise ValueError("response exceeds configured maximum size")
                try:
                    body = response.json() if raw else {}
                except json.JSONDecodeError as exc:
                    raise ValueError("business API returned invalid JSON") from exc
                return {
                    "status_code": response.status_code,
                    "ok": response.is_success,
                    "body": body,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "url": url,
                    "method": method,
                    "credential_env": self.config.token_env,
                    "attempts": attempt + 1,
                }
            except (httpx.HTTPError, OSError) as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    raise
                self._sleep_before_retry(attempt)
        raise last_error or RuntimeError("business action failed")
