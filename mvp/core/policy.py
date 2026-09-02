from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ActionRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class ActionPolicy:
    risk: ActionRisk
    requires_approval: bool
    allowed: bool
    reason: str


def evaluate_action(action_type: str, *, amount: float | None = None) -> ActionPolicy:
    """Default-deny policy for future autonomous actions.

    The MVP intentionally permits only reversible, low-impact actions without
    direct execution. Financial transfers, irreversible changes, and privilege
    changes are always gated.
    """
    normalized = action_type.strip().lower()

    if normalized in {"draft_email", "create_task", "prepare_report"}:
        return ActionPolicy(ActionRisk.LOW, True, True, "Reversible business action; human approval remains required.")

    if normalized in {"send_email", "update_crm", "change_purchase_order"}:
        return ActionPolicy(ActionRisk.MEDIUM, True, True, "External or business-state change requires explicit approval.")

    if normalized in {"transfer_money", "refund_money", "delete_data", "change_permissions"}:
        return ActionPolicy(ActionRisk.CRITICAL, True, False, "Critical action is blocked in the MVP until production controls exist.")

    if amount is not None and amount > 0:
        return ActionPolicy(ActionRisk.HIGH, True, False, "Monetary impact is blocked by default in the MVP.")

    return ActionPolicy(ActionRisk.HIGH, True, False, "Unknown action type is denied by default.")
