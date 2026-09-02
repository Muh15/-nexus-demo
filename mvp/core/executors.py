from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .models import BusinessContext, Evidence
from .planner import ActionPlan


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    action_type: str
    status: str
    message: str
    evidence: list[Evidence] = field(default_factory=list)
    output: dict[str, Any] = field(default_factory=dict)


ActionHandler = Callable[[ActionPlan, BusinessContext], ExecutionResult]


class ActionExecutor:
    """Policy-aware execution boundary. Handlers perform only explicit actions."""

    def __init__(self, handlers: dict[str, ActionHandler] | None = None) -> None:
        self._handlers = dict(handlers or {})

    def register(self, action_type: str, handler: ActionHandler) -> None:
        if action_type in self._handlers:
            raise ValueError(f"action handler already registered: {action_type}")
        self._handlers[action_type] = handler

    def execute(self, plan: ActionPlan, context: BusinessContext) -> ExecutionResult:
        if not plan.policy.allowed:
            return ExecutionResult(plan.action_type, "blocked", plan.policy.reason)
        handler = self._handlers.get(plan.action_type)
        if handler is None:
            return ExecutionResult(plan.action_type, "unavailable", "No action handler is registered.")
        return handler(plan, context)


def draft_email_handler(plan: ActionPlan, context: BusinessContext) -> ExecutionResult:
    """Create a reversible draft artifact; never sends externally."""
    target = plan.payload.get("target") or "unknown recipient"
    evidence_ids = list(context.evidence)[:10]
    evidence = [
        Evidence(
            id=f"execution:draft_email:{index}",
            source="action_executor",
            claim="draft_email_created",
            value={"target": target, "description": plan.description},
            confidence=100,
            metadata={"evidence_ids": evidence_ids, "reversible": True},
        )
        for index, _ in enumerate(evidence_ids or [None], start=1)
    ]
    return ExecutionResult(
        action_type="draft_email",
        status="completed",
        message="Draft created; no external message was sent.",
        evidence=evidence,
        output={"target": target, "sent": False, "draft": plan.description},
    )
