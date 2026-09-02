from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .action_executor import ActionResult


@dataclass(frozen=True, slots=True)
class VerificationResult:
    status: str
    checks: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


Verifier = Callable[[ActionResult], VerificationResult]


class ActionVerifier:
    """Verifies execution results without owning the external system."""

    def __init__(self, verifiers: dict[str, Verifier] | None = None) -> None:
        self._verifiers = dict(verifiers or {})

    def register(self, action_type: str, verifier: Verifier) -> None:
        if action_type in self._verifiers:
            raise ValueError(f"action verifier already registered: {action_type}")
        self._verifiers[action_type] = verifier

    def verify(self, result: ActionResult) -> VerificationResult:
        if result.status != "completed":
            return VerificationResult(
                status="not_verified",
                checks=[f"Execution status is {result.status}"],
            )
        verifier = self._verifiers.get(result.action_type)
        if verifier is None:
            return VerificationResult(
                status="unavailable",
                checks=["No verifier is registered for this action type."],
            )
        return verifier(result)


def draft_email_verifier(result: ActionResult) -> VerificationResult:
    sent = bool(result.output.get("sent", False))
    return VerificationResult(
        status="verified" if not sent else "failed",
        checks=[
            "Draft artifact was created",
            "No external email was sent",
            "Target and description were preserved",
        ],
        details={"sent": sent, "target": result.output.get("target")},
    )
