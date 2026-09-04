from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable
from uuid import uuid4

from .authorization import authorize_execution, separation_of_duties_enabled
from .planner import ActionPlan, action_fingerprint


@dataclass(frozen=True, slots=True)
class ActionResult:
    action_type: str
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    execution_id: str | None = None


ActionHandler = Callable[[ActionPlan], ActionResult]


class ActionExecutor:
    """Executes policy-approved actions through an authorized core boundary."""

    def __init__(self, handlers: dict[str, ActionHandler] | None = None) -> None:
        self._handlers = dict(handlers or {})

    def register(self, action_type: str, handler: ActionHandler) -> None:
        if action_type in self._handlers:
            raise ValueError(f"action handler already registered: {action_type}")
        self._handlers[action_type] = handler

    @staticmethod
    def _approval_is_bound(plan: ActionPlan) -> bool:
        required = bool(plan.policy.requires_approval)
        payload_required = bool(plan.payload.get("approval_required"))
        if payload_required != required:
            return False
        if not required:
            return True
        expected = str(plan.payload.get("action_fingerprint", ""))
        actual = action_fingerprint(plan.action_type, plan.payload.get("target"), dict(plan.payload.get("body", {})))
        approved = str(plan.payload.get("approved_fingerprint", ""))
        return bool(plan.payload.get("approved") and expected and expected == actual and approved == actual)

    @staticmethod
    def _separation_is_valid(plan: ActionPlan, actor_subject: str | None) -> bool:
        if not separation_of_duties_enabled():
            return True
        approver = str(plan.payload.get("approved_by_subject", "")).strip()
        return bool(approver and actor_subject and approver != actor_subject)

    def execute(
        self,
        plan: ActionPlan,
        *,
        tenant_id: str | None = None,
        actor_role: str | None = None,
        actor_subject: str | None = None,
    ) -> ActionResult:
        authorization = authorize_execution(
            plan.action_type,
            tenant_id=tenant_id,
            plan_tenant_id=plan.payload.get("tenant_id"),
            actor_role=actor_role,
        )
        if not authorization.allowed:
            return ActionResult(action_type=plan.action_type, status="blocked", message=authorization.reason)
        if not plan.policy.allowed:
            return ActionResult(action_type=plan.action_type, status="blocked", message=plan.policy.reason)
        if plan.policy.requires_approval and not plan.payload.get("approved"):
            return ActionResult(action_type=plan.action_type, status="awaiting_approval", message="Explicit approval is required before execution.")
        if not self._approval_is_bound(plan):
            return ActionResult(action_type=plan.action_type, status="blocked", message="Approval is no longer valid because the action payload or approval requirement changed; fingerprint must match.")
        if not self._separation_is_valid(plan, actor_subject):
            return ActionResult(action_type=plan.action_type, status="blocked", message="Execution requires a different principal from the approver.")
        handler = self._handlers.get(plan.action_type)
        if handler is None:
            return ActionResult(action_type=plan.action_type, status="unavailable", message="No execution handler is registered for this action type.")
        execution_id = plan.payload.get("execution_id") or f"EXE-{uuid4().hex[:12].upper()}"
        executable_plan = replace(plan, payload={**plan.payload, "execution_id": execution_id})
        result = handler(executable_plan)
        if result.execution_id is None:
            return replace(result, execution_id=execution_id)
        return result


def draft_email_handler(plan: ActionPlan) -> ActionResult:
    """Safe MVP handler: creates an artifact but does not send anything."""
    return ActionResult(
        action_type=plan.action_type,
        status="completed",
        output={"kind": "email_draft", "target": plan.payload.get("target"), "description": plan.description, "sent": False},
        message="Created a reversible email draft; nothing was sent.",
    )
