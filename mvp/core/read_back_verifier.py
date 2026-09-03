from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen

from .action_executor import ActionResult
from .verifier import VerificationResult


@dataclass(frozen=True, slots=True)
class ReadBackConfig:
    base_url: str
    endpoint: str
    allowed_hosts: frozenset[str]
    method: str = "GET"
    timeout_seconds: float = 10.0
    max_response_bytes: int = 2_000_000
    response_path: str = ""
    expected_path: str = "request_body"
    execution_id_path: str | None = None
    require_execution_id_match: bool = False

    def __post_init__(self) -> None:
        if self.method.upper() != "GET":
            raise ValueError("read-after-write verification only supports GET")
        if not self.allowed_hosts:
            raise ValueError("read-after-write verification requires an allow-list")
        for url in (self.base_url, urljoin(self.base_url.rstrip("/") + "/", self.endpoint.lstrip("/"))):
            host = urlparse(url).hostname
            if not host or host not in self.allowed_hosts:
                raise ValueError("verification URL host is not allow-listed")
        if self.max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")


def _path_get(value: Any, path: str) -> Any:
    current = value
    for part in [item for item in path.strip(".").split(".") if item]:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise KeyError(path)
    return current


class ReadAfterWriteVerifier:
    """Performs a bounded, allow-listed GET and compares observed state with the action request state."""

    def __init__(self, config: ReadBackConfig) -> None:
        self.config = config

    def _url(self, result: ActionResult) -> str:
        target = str(result.output.get("target") or "")
        endpoint = self.config.endpoint.format(
            target=quote(target, safe=""),
            execution_id=quote(str(result.execution_id or ""), safe=""),
        )
        url = urljoin(self.config.base_url.rstrip("/") + "/", endpoint.lstrip("/"))
        host = urlparse(url).hostname
        if not host or host not in self.config.allowed_hosts:
            raise ValueError("verification URL host is not allow-listed")
        return url

    def verify(self, result: ActionResult) -> VerificationResult:
        url = self._url(result)
        request = Request(url, method="GET", headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read(self.config.max_response_bytes + 1)
                if len(raw) > self.config.max_response_bytes:
                    return VerificationResult(
                        status="failed",
                        checks=["Read-back response exceeded the configured size limit."],
                        details={"execution_id": result.execution_id},
                    )
                payload = json.loads(raw.decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            return VerificationResult(
                status="failed",
                checks=["Read-back request failed."],
                details={"error_type": type(exc).__name__, "execution_id": result.execution_id},
            )

        if self.config.require_execution_id_match:
            if not self.config.execution_id_path:
                return VerificationResult(status="failed", checks=["Execution ID path is required for strict identity verification."])
            try:
                observed_execution_id = _path_get(payload, self.config.execution_id_path)
            except KeyError:
                return VerificationResult(status="failed", checks=["Execution ID was not present in read-back state."], details={"execution_id": result.execution_id})
            if str(observed_execution_id) != str(result.execution_id):
                return VerificationResult(
                    status="failed",
                    checks=["Read-back execution ID does not match the executed action."],
                    details={"expected_execution_id": result.execution_id, "observed_execution_id": observed_execution_id},
                )

        try:
            observed = _path_get(payload, self.config.response_path) if self.config.response_path else payload
            expected = _path_get(result.output, self.config.expected_path)
        except KeyError as exc:
            return VerificationResult(
                status="failed",
                checks=["Configured verification state path was not found."],
                details={"missing_path": str(exc), "execution_id": result.execution_id},
            )

        matched = observed == expected
        return VerificationResult(
            status="verified" if matched else "failed",
            checks=[
                "External read-back completed successfully",
                "Observed business state matches the expected post-action state" if matched else "Observed business state does not match the expected post-action state",
            ],
            details={
                "execution_id": result.execution_id,
                "url_host": urlparse(url).hostname,
                "observed": observed,
                "expected": expected,
            },
        )


def build_read_back_verifier_from_env() -> ReadAfterWriteVerifier | None:
    base_url = os.getenv("NEXUS_VERIFY_URL", "").strip()
    endpoint = os.getenv("NEXUS_VERIFY_ENDPOINT", "").strip()
    allowed_hosts = frozenset(host.strip() for host in os.getenv("NEXUS_HTTP_ALLOWED_HOSTS", "").split(",") if host.strip())
    if not base_url or not endpoint or not allowed_hosts:
        return None
    config = ReadBackConfig(
        base_url=base_url,
        endpoint=endpoint,
        allowed_hosts=allowed_hosts,
        timeout_seconds=float(os.getenv("NEXUS_VERIFY_TIMEOUT_SECONDS", "10")),
        max_response_bytes=int(os.getenv("NEXUS_VERIFY_MAX_BYTES", "2000000")),
        response_path=os.getenv("NEXUS_VERIFY_RESPONSE_PATH", "").strip(),
        expected_path=os.getenv("NEXUS_VERIFY_EXPECTED_PATH", "request_body").strip(),
        execution_id_path=os.getenv("NEXUS_VERIFY_EXECUTION_ID_PATH", "").strip() or None,
        require_execution_id_match=os.getenv("NEXUS_VERIFY_REQUIRE_EXECUTION_ID_MATCH", "false").strip().lower() in {"1", "true", "yes"},
    )
    return ReadAfterWriteVerifier(config)
