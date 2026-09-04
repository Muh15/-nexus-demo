from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable, Protocol
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


class ActionExecutionStore(Protocol):
    def claim_action_execution(self, *, execution_id: str, tenant_id: str, action_type: str, action_fingerprint: str, created_at: str) -> tuple[str, dict[str, Any] | None]: ...
    def complete_action_execution(self, *, execution_id: str, tenant_id: str, result: dict[str, Any], updated_at: str) -> bool: ...
    def release_action_execution(self, *, execution_id: str, tenant_id: str) -> bool: ...


ActionHandler = Callable[[ActionPlan], ActionResult]


class ActionExecutor:
    """Executes policy-approved actions through an authorized core boundary."""

    def __init__(self, handlers: dict[str, ActionHandler] | None = None, execution_store: ActionExecutionStore | None = None) -> None:
        self._handlers = dict(handlers or {})
        self._execution_store = execution_store

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

    @staticmethod
    def _stored_result(action_type: str, execution_id: str, stored: dict[str, Any]) -> ActionResult:
        return ActionResult(
            action_type=str(stored.get("action_type", action_type)),
            status=str(stored.get("status", "completed")),
            output=dict(stored.get("output", {})),
            message=str(stored.get("message", "Replayed previously completed action.")),
            execution_id=str(stored.get("execution_id", execution_id)),
        )

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
            return ActionResult(action_type=plan.action_type, status="blocked", message="Approval is no longer valid: payload changed or approval requirement changed; fingerprint must match.")
        if not self._separation_is_valid(plan, actor_subject):
            return ActionResult(action_type=plan.action_type, status="blocked", message="Execution requires a different principal from the approver.")
        handler = self._handlers.get(plan.action_type)
        if handler is None:
            return ActionResult(action_type=plan.action_type, status="unavailable", message="No execution handler is registered for this action type.")

        execution_id = str(plan.payload.get("execution_id") or f"EXE-{uuid4().hex[:12].upper()}")
        executable_plan = replace(plan, payload={**plan.payload, "execution_id": execution_id})
        if self._execution_store is not None:
            fingerprint = action_fingerprint(plan.action_type, plan.payload.get("target"), dict(plan.payload.get("body", {})))
            effective_tenant = str(tenant_id or plan.payload.get("tenant_id") or "default")
            state, stored = self._execution_store.claim_action_execution(
                execution_id=execution_id,
                tenant_id=effective_tenant,
                action_type=plan.action_type,
                action_fingerprint=fingerprint,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            if state == "completed" and stored is not None:
                return self._stored_result(plan.action_type, execution_id, stored)
            if state == "in_progress":
                return ActionResult(action_type=plan.action_type, status="blocked", message="Execution is already in progress for this execution_id.", execution_id=execution_id)
            if state == "conflict":
                return ActionResult(action_type=plan.action_type, status="blocked", message="execution_id is already bound to a different action or tenant.", execution_id=execution_id)
            try:
                result = handler(executable_plan)
            except Exception:
                self._execution_store.release_action_execution(execution_id=execution_id, tenant_id=effective_tenant)
                raise
            if result.execution_id is None:
                result = replace(result, execution_id=execution_id)
            if result.status == "completed":
                stored_result = {
                    "action_type": result.action_type,
                    "status": result.status,
                    "output": result.output,
                    "message": result.message,
                    "execution_id": result.execution_id,
                }
                self._execution_store.complete_action_execution(
                    execution_id=execution_id,
                    tenant_id=effective_tenant,
                    result=stored_result,
                    updated_at=datetime.now(timezone.utc).isoformat(),
                )
            else:
                self._execution_store.release_action_execution(execution_id=execution_id, tenant_id=effective_tenant)
            return result

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
