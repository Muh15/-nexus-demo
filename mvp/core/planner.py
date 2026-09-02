from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .policy import ActionPolicy, evaluate_action


@dataclass(frozen=True, slots=True)
class ActionPlan:
    action_type: str
    description: str
    policy: ActionPolicy
    payload: dict[str, Any]


def plan_action(recommended_action: str, *, target: str | None = None) -> ActionPlan:
    """Translate a decision into a safe, explicit action plan.

    This layer separates *what NEXUS recommends* from *what it is allowed to
    execute*. That distinction becomes critical as connectors gain write
    access to real customer systems.
    """
    action_type = "draft_email"
    policy = evaluate_action(action_type)
    return ActionPlan(
        action_type=action_type,
        description=recommended_action,
        policy=policy,
        payload={
            "target": target,
            "approval_required": policy.requires_approval,
            "execution_allowed": policy.allowed,
        },
    )
