from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable
from uuid import uuid4

from .planner import ActionPlan


@dataclass(frozen=True, slots=True)
class ActionResult:
    action_type: str
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    execution_id: str | None = None


ActionHandler = Callable[[ActionPlan], ActionResult]


class ActionExecutor:
    """Executes only policy-approved actions through replaceable handlers."""

    def __init__(self, handlers: dict[str, ActionHandler] | None = None) -> None:
        self._handlers = dict(handlers or {})

    def register(self, action_type: str, handler: ActionHandler) -> None:
        if action_type in self._handlers:
            raise ValueError(f"action handler already registered: {action_type}")
        self._handlers[action_type] = handler

    def execute(self, plan: ActionPlan) -> ActionResult:
        if not plan.policy.allowed:
            return ActionResult(
                action_type=plan.action_type,
                status="blocked",
                message=plan.policy.reason,
            )
        if plan.payload.get("approval_required") and not plan.payload.get("approved"):
            return ActionResult(
                action_type=plan.action_type,
                status="awaiting_approval",
                message="Explicit approval is required before execution.",
            )
        handler = self._handlers.get(plan.action_type)
        if handler is None:
            return ActionResult(
                action_type=plan.action_type,
                status="unavailable",
                message="No execution handler is registered for this action type.",
            )
        result = handler(plan)
        if result.status == "completed" and result.execution_id is None:
            return replace(result, execution_id=f"EXE-{uuid4().hex[:12].upper()}")
        return result


def draft_email_handler(plan: ActionPlan) -> ActionResult:
    """Safe MVP handler: creates an artifact but does not send anything."""
    return ActionResult(
        action_type=plan.action_type,
        status="completed",
        output={
            "kind": "email_draft",
            "target": plan.payload.get("target"),
            "description": plan.description,
            "sent": False,
        },
        message="Created a reversible email draft; nothing was sent.",
    )
