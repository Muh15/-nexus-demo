from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable
from uuid import uuid4

from .context_builder import build_context
from .goal_planner import GoalPlan, build_goal_plan, parse_goal
from .impact import ImpactAssessment
from .intelligence_graph import IntelligenceGraph
from .mission_intelligence import MissionIntelligence
from .models import BusinessContext, utc_now
from .planner import ActionPlan, plan_action
from .research_executor import ResearchExecutor, ResearchResult
from .research_planner import ResearchPlan, build_research_plan


@dataclass(slots=True)
class MissionState:
    """Explicit lifecycle state for a NEXUS mission.

    The orchestrator owns workflow state only; domain reasoning, connectors,
    memory, graph projection, research, actions, and verification remain replaceable.
    """

    id: str
    tenant_id: str
    goal: str
    constraints: list[str] = field(default_factory=list)
    stage: str = "created"
    context: BusinessContext = field(default_factory=BusinessContext)
    goal_plan: GoalPlan | None = None
    intelligence_graph: IntelligenceGraph | None = None
    impact_assessments: list[ImpactAssessment] = field(default_factory=list)
    research_plan: ResearchPlan | None = None
    research_results: list[ResearchResult] = field(default_factory=list)
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

    def __init__(
        self,
        reasoner: Reasoner,
        *,
        intelligence: MissionIntelligence | None = None,
        research_executor: ResearchExecutor | None = None,
    ) -> None:
        self._reasoner = reasoner
        self._intelligence = intelligence or MissionIntelligence()
        self._research_executor = research_executor or ResearchExecutor()

    def create(
        self,
        *,
        tenant_id: str,
        goal: str,
        constraints: Iterable[str] = (),
        records: Iterable[dict[str, Any]] = (),
        source: str = "unknown",
    ) -> MissionState:
        records = list(records)
        constraints = list(constraints)
        mission = MissionState(
            id=f"NXS-{uuid4().hex[:10].upper()}",
            tenant_id=tenant_id,
            goal=goal,
            constraints=constraints,
        )
        mission.transition("observe", "بدأ جمع الإشارات المرتبطة بالمهمة.")

        mission.goal_plan = build_goal_plan(parse_goal(goal, constraints))
        mission.context = build_context(records, source=source)
        mission.intelligence_graph = IntelligenceGraph.from_context(mission.context)
        _, _, assessments = self._intelligence.prepare(
            tenant_id=tenant_id,
            goal_text=goal,
            constraints=constraints,
            records=records,
            source=source,
        )
        mission.impact_assessments = assessments
        mission.research_plan = build_research_plan(
            mission.goal_plan,
            mission.context,
            assessments,
        )

        mission.transition(
            "understand",
            "تم بناء السياق وخريطة الأدلة وتحديد فجوات المعلومات قبل القرار.",
            entities=len(mission.context.entities),
            relationships=len(mission.context.relationships),
            evidence=len(mission.context.evidence),
            research_domains=mission.goal_plan.domains() if mission.goal_plan else [],
            relevant_changes=sum(1 for item in assessments if item.relevant),
            research_tasks=len(mission.research_plan.pending()) if mission.research_plan else 0,
        )
        return mission

    def research(self, mission: MissionState) -> MissionState:
        if mission.stage not in {"understand", "researched"}:
            raise ValueError(f"Cannot research from stage: {mission.stage}")
        if mission.research_plan is None:
            raise ValueError("Research plan is required before execution")

        mission.transition(
            "researching",
            "يتم جمع الأدلة اللازمة لسد فجوات المعلومات قبل القرار.",
            task_count=len(mission.research_plan.pending()),
        )
        mission.research_results = self._research_executor.execute(
            mission.research_plan,
            mission.context,
        )
        for result in mission.research_results:
            for evidence in result.evidence:
                mission.context.add_evidence(evidence)

        unavailable = sum(1 for result in mission.research_results if result.status == "unavailable")
        completed = sum(1 for result in mission.research_results if result.status == "completed")
        mission.transition(
            "researched",
            "انتهت دورة البحث ويمكن الآن تقييم كفاية الأدلة.",
            completed=completed,
            unavailable=unavailable,
            evidence_added=sum(len(result.evidence) for result in mission.research_results),
        )
        return mission

    def decide(self, mission: MissionState) -> MissionState:
        if mission.stage not in {"understand", "researched", "reason"}:
            raise ValueError(f"Cannot decide from stage: {mission.stage}")
        mission.transition("reason", "يتم تقييم الإشارات والقيود والتغيّرات والأدلة المتاحة.")
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
        mission.verification = {"status": "pending", "checks": []}
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
