from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .policy import ActionPolicy, evaluate_action


@dataclass(frozen=True, slots=True)
class ActionPlan:
    """Explicit proposed action plus its policy decision."""

    action_type: str
    description: str
    policy: ActionPolicy
    payload: dict[str, Any]


def action_fingerprint(action_type: str, target: str | None, body: dict[str, Any]) -> str:
    """Stable hash binding approval to the exact proposed business action."""
    canonical = json.dumps(
        {"action_type": action_type.strip().lower(), "target": target, "body": body},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def plan_action(
    recommended_action: str,
    *,
    target: str | None = None,
    action_type: str = "draft_email",
    amount: float | None = None,
    body: dict[str, Any] | None = None,
) -> ActionPlan:
    """Translate a decision into a policy-checked, explicit action plan."""
    normalized_body = dict(body or {})
    policy = evaluate_action(action_type, amount=amount)
    fingerprint = action_fingerprint(action_type, target, normalized_body)
    return ActionPlan(
        action_type=action_type,
        description=recommended_action,
        policy=policy,
        payload={
            "target": target,
            "body": normalized_body,
            "approval_required": policy.requires_approval,
            "execution_allowed": policy.allowed,
            "risk": policy.risk.value,
            "action_fingerprint": fingerprint,
        },
    )
