from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class AuthorizationDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    decision: AuthorizationDecision
    reason: str

    @property
    def allowed(self) -> bool:
        return self.decision is AuthorizationDecision.ALLOW


_EXECUTION_ROLES: dict[str, frozenset[str]] = {
    "draft_email": frozenset({"operator", "admin"}),
    "create_task": frozenset({"operator", "admin"}),
    "prepare_report": frozenset({"operator", "admin"}),
    "send_email": frozenset({"operator", "admin"}),
    "update_crm": frozenset({"operator", "admin"}),
    "change_purchase_order": frozenset({"operator", "admin"}),
}
_APPROVAL_ROLES = frozenset({"approver", "admin"})


def _strict_role_mode() -> bool:
    return os.getenv("NEXUS_AUTH_REQUIRED", "false").strip().lower() in {"1", "true", "yes", "on"}


def authorize_execution(
    action_type: str,
    *,
    tenant_id: str | None,
    plan_tenant_id: str | None,
    actor_role: str | None,
) -> AuthorizationResult:
    """Authorize execution at the core boundary, not only at HTTP routes."""
    normalized = action_type.strip().lower()
    roles = _EXECUTION_ROLES.get(normalized)
    if roles is None:
        return AuthorizationResult(AuthorizationDecision.DENY, "Action type is not authorized for execution.")
    # Tenant context is security-critical: when strict auth is enabled, both sides
    # must be present. In every mode, a supplied context must match exactly.
    if tenant_id and plan_tenant_id and tenant_id != plan_tenant_id:
        return AuthorizationResult(AuthorizationDecision.DENY, "Action plan tenant does not match the execution tenant.")
    if _strict_role_mode() and (not tenant_id or not plan_tenant_id or not actor_role):
        return AuthorizationResult(AuthorizationDecision.DENY, "Authenticated tenant, plan tenant, and role are required for execution.")
    if actor_role is not None and actor_role.strip().lower() not in roles:
        return AuthorizationResult(AuthorizationDecision.DENY, f"Role '{actor_role}' is not authorized to execute this action.")
    return AuthorizationResult(AuthorizationDecision.ALLOW, "Execution is authorized for the current principal and tenant.")


def authorize_approval(*, actor_role: str | None) -> AuthorizationResult:
    """Authorize who may approve an action plan."""
    if _strict_role_mode() and not actor_role:
        return AuthorizationResult(AuthorizationDecision.DENY, "Authenticated approver role is required.")
    if actor_role is not None and actor_role.strip().lower() not in _APPROVAL_ROLES:
        return AuthorizationResult(AuthorizationDecision.DENY, f"Role '{actor_role}' is not authorized to approve actions.")
    return AuthorizationResult(AuthorizationDecision.ALLOW, "Approval is authorized for the current principal.")


def separation_of_duties_enabled() -> bool:
    return os.getenv("NEXUS_SEPARATION_OF_DUTIES", "false").strip().lower() in {"1", "true", "yes", "on"}
