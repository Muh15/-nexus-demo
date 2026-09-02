from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable
from uuid import uuid4

from .context_builder import build_context
from .models import BusinessContext, utc_now
from .planner import ActionPlan, plan_action


@dataclass(slots=True)
class MissionState:
    """Explicit lifecycle state for a NEXUS mission.

    The orchestrator owns workflow state only; domain reasoning, connectors,
    actions, and verification remain replaceable components.
    """

    id: str
    tenant_id: str
    goal: str
    constraints: list[str] = field(default_factory=list)
    stage: str = "created"
    context: BusinessContext = field(default_factory=BusinessContext)
    decision: dict[str, Any] | None = None
    action_plan: ActionPlan | None = None
    verification: dict[str, Any] | None = None
    audit: list[dict[str, Any]] = field(default_factory=list)

    def log(self, stage: str, message: str, **metadata: Any) -> None:
        self.audit.append({
            "timestamp": utc_now(),
            "stage": stage,
            "message": message,
            "metadata": metadata,
        })

    def transition(self, stage: str, message: str, **metadata: Any) -> None:
        self.stage = stage
        self.log(stage, message, **metadata)


Reasoner = Callable[[str, list[str], BusinessContext], dict[str, Any]]


class MissionOrchestrator:
    """Coordinates the NEXUS lifecycle without owning business logic."""

    def __init__(self, reasoner: Reasoner) -> None:
        self._reasoner = reasoner

    def create(
        self,
        *,
        tenant_id: str,
        goal: str,
        constraints: Iterable[str] = (),
        records: Iterable[dict[str, Any]] = (),
        source: str = "unknown",
    ) -> MissionState:
        mission = MissionState(
            id=f"NXS-{uuid4().hex[:10].upper()}",
            tenant_id=tenant_id,
            goal=goal,
            constraints=list(constraints),
        )
        mission.transition("observe", "بدأ جمع الإشارات المرتبطة بالمهمة.")
        mission.context = build_context(records, source=source)
        mission.transition(
            "understand",
            "تم بناء سياق أعمال قابل للتتبع.",
            entities=len(mission.context.entities),
            relationships=len(mission.context.relationships),
            evidence=len(mission.context.evidence),
        )
        return mission

    def decide(self, mission: MissionState) -> MissionState:
        if mission.stage not in {"understand", "reason"}:
            raise ValueError(f"Cannot decide from stage: {mission.stage}")
        mission.transition("reason", "يتم تقييم الإشارات والقيود.")
        mission.decision = self._reasoner(mission.goal, mission.constraints, mission.context)
        mission.transition("decide", "اكتمل القرار وأصبح جاهزًا لتخطيط الإجراء.")
        return mission

    def plan(self, mission: MissionState, *, target: str | None = None) -> MissionState:
        if mission.stage != "decide" or not mission.decision:
            raise ValueError("Decision is required before action planning")
        recommended = str(mission.decision.get("recommended_action", ""))
        mission.action_plan = plan_action(recommended, target=target)
        mission.transition("action_planned", "تم إنشاء خطة إجراء منفصلة عن القرار.")
        return mission

    def approve(self, mission: MissionState) -> MissionState:
        if mission.stage != "action_planned" or mission.action_plan is None:
            raise ValueError("Action plan is required before approval")
        if not mission.action_plan.policy.allowed:
            raise PermissionError("Action is blocked by policy")
        mission.transition("approved", "تم اعتماد الإجراء وفق سياسة NEXUS.")
        return mission

    def complete_demo_execution(self, mission: MissionState) -> MissionState:
        if mission.stage != "approved":
            raise ValueError("Mission must be approved before execution")
        mission.transition("executed", "تم تنفيذ الإجراء التجريبي الآمن.")
        mission.verification = {
            "status": "pending",
            "checks": [],
        }
        return mission

    def verify_demo(self, mission: MissionState) -> MissionState:
        if mission.stage != "executed":
            raise ValueError("Mission must be executed before verification")
        mission.verification = {
            "status": "verified",
            "checks": [
                "الإجراء مرتبط بالقرار الأصلي",
                "السياسة سمحت بالإجراء",
                "سجل التدقيق محفوظ",
            ],
        }
        mission.transition("verified", "تم التحقق وإغلاق دورة المهمة.")
        return mission
