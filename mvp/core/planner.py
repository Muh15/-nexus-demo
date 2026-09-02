from __future__ import annotations

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


def plan_action(
    recommended_action: str,
    *,
    target: str | None = None,
    action_type: str = "draft_email",
    amount: float | None = None,
) -> ActionPlan:
    """Translate a decision into a policy-checked, explicit action plan.

    The planner never executes anything. It only describes a possible action
    and asks the policy boundary whether that action is permitted in the
    current environment.
    """
    policy = evaluate_action(action_type, amount=amount)
    return ActionPlan(
        action_type=action_type,
        description=recommended_action,
        policy=policy,
        payload={
            "target": target,
            "approval_required": policy.requires_approval,
            "execution_allowed": policy.allowed,
            "risk": policy.risk.value,
        },
    )
