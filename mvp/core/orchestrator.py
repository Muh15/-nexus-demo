from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable
from uuid import uuid4

from .action_executor import ActionExecutor, ActionResult, draft_email_handler
from .context_builder import build_context
from .goal_planner import GoalPlan, build_goal_plan, parse_goal
from .impact import ImpactAssessment
from .intelligence_graph import IntelligenceGraph
from .mission_intelligence import MissionIntelligence
from .models import BusinessContext, utc_now
from .planner import ActionPlan, plan_action
from .research_executor import ResearchExecutor, ResearchResult
from .research_planner import ResearchPlan, build_research_plan
from .verifier import ActionVerifier, VerificationResult, draft_email_verifier


@dataclass(slots=True)
class MissionState:
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
    action_result: ActionResult | None = None
    verification: VerificationResult | None = None
    audit: list[dict[str, Any]] = field(default_factory=list)

    def log(self, stage: str, message: str, **metadata: Any) -> None:
        self.audit.append({"timestamp": utc_now(), "stage": stage, "message": message, "metadata": metadata})

    def transition(self, stage: str, message: str, **metadata: Any) -> None:
        self.stage = stage
        self.log(stage, message, **metadata)

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "goal": self.goal,
            "constraints": list(self.constraints),
            "stage": self.stage,
            "context": _plain(self.context),
            "goal_plan": _plain(self.goal_plan),
            "intelligence_graph": _plain(self.intelligence_graph),
            "impact_assessments": _plain(self.impact_assessments),
            "research_plan": _plain(self.research_plan),
            "research_results": _plain(self.research_results),
            "decision": _plain(self.decision),
            "action_plan": _plain(self.action_plan),
            "action_result": _plain(self.action_result),
            "verification": _plain(self.verification),
            "audit": _plain(self.audit),
        }


Reasoner = Callable[[str, list[str], BusinessContext], dict[str, Any]]


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if hasattr(value, "model_dump"):
        return _plain(value.model_dump(mode="json"))
    if hasattr(value, "__dataclass_fields__"):
        return {name: _plain(getattr(value, name)) for name in value.__dataclass_fields__}
    return str(value)


def mission_from_snapshot(snapshot: dict[str, Any]) -> MissionState:
    """Restore a persisted mission snapshot without coupling storage to API models."""
    required = ("id", "tenant_id", "goal", "stage")
    missing = [field for field in required if field not in snapshot]
    if missing:
        raise ValueError(f"Mission snapshot missing fields: {', '.join(missing)}")
    mission = MissionState(
        id=str(snapshot["id"]),
        tenant_id=str(snapshot["tenant_id"]),
        goal=str(snapshot["goal"]),
        constraints=[str(item) for item in snapshot.get("constraints", [])],
        stage=str(snapshot.get("stage", "created")),
        audit=list(snapshot.get("audit", [])),
    )
    return mission


class MissionOrchestrator:
    """Coordinates the NEXUS lifecycle while keeping capabilities replaceable."""

    def __init__(
        self,
        reasoner: Reasoner,
        *,
        intelligence: MissionIntelligence | None = None,
        research_executor: ResearchExecutor | None = None,
        action_executor: ActionExecutor | None = None,
        verifier: ActionVerifier | None = None,
    ) -> None:
        self._reasoner = reasoner
        self._intelligence = intelligence or MissionIntelligence()
        self._research_executor = research_executor or ResearchExecutor()
        self._action_executor = action_executor or ActionExecutor({"draft_email": draft_email_handler})
        self._verifier = verifier or ActionVerifier({"draft_email": draft_email_verifier})

    @property
    def action_executor(self) -> ActionExecutor:
        return self._action_executor

    @property
    def verifier(self) -> ActionVerifier:
        return self._verifier

    @property
    def research_executor(self) -> ResearchExecutor:
        return self._research_executor

    def create(self, *, tenant_id: str, goal: str, constraints: Iterable[str] = (), records: Iterable[dict[str, Any]] = (), source: str = "unknown") -> MissionState:
        records = list(records)
        constraints = list(constraints)
        mission = MissionState(id=f"NXS-{uuid4().hex[:10].upper()}", tenant_id=tenant_id, goal=goal, constraints=constraints)
        mission.transition("observe", "بدأ جمع الإشارات المرتبطة بالمهمة.")
        mission.goal_plan = build_goal_plan(parse_goal(goal, constraints))
        mission.context = build_context(records, source=source)
        mission.intelligence_graph = IntelligenceGraph.from_context(mission.context)
        _, _, assessments = self._intelligence.prepare(tenant_id=tenant_id, goal_text=goal, constraints=constraints, records=records, source=source)
        mission.impact_assessments = assessments
        mission.research_plan = build_research_plan(mission.goal_plan, mission.context, assessments)
        mission.transition("understand", "تم بناء السياق وخريطة الأدلة وتحديد فجوات المعلومات قبل القرار.", entities=len(mission.context.entities), relationships=len(mission.context.relationships), evidence=len(mission.context.evidence), research_domains=mission.goal_plan.domains() if mission.goal_plan else [], relevant_changes=sum(1 for item in assessments if item.relevant), research_tasks=len(mission.research_plan.pending()) if mission.research_plan else 0)
        return mission

    def research(self, mission: MissionState) -> MissionState:
        if mission.stage not in {"understand", "researched"}:
            raise ValueError(f"Cannot research from stage: {mission.stage}")
        if mission.research_plan is None:
            raise ValueError("Research plan is required before execution")
        mission.transition("researching", "يتم جمع الأدلة اللازمة لسد فجوات المعلومات قبل القرار.", task_count=len(mission.research_plan.pending()))
        mission.research_results = self._research_executor.execute(mission.research_plan, mission.context)
        for result in mission.research_results:
            for evidence in result.evidence:
                mission.context.add_evidence(evidence)
        unavailable = sum(1 for result in mission.research_results if result.status == "unavailable")
        completed = sum(1 for result in mission.research_results if result.status == "completed")
        mission.transition("researched", "انتهت دورة البحث ويمكن الآن تقييم كفاية الأدلة.", completed=completed, unavailable=unavailable, evidence_added=sum(len(result.evidence) for result in mission.research_results))
        return mission

    def decide(self, mission: MissionState) -> MissionState:
        if mission.stage not in {"understand", "researched", "reason"}:
            raise ValueError(f"Cannot decide from stage: {mission.stage}")
        mission.transition("reason", "يتم تقييم الإشارات والقيود والتغيّرات والأدلة المتاحة.")
        mission.decision = self._reasoner(mission.goal, mission.constraints, mission.context)
        mission.transition("decide", "اكتمل القرار وأصبح جاهزًا لتخطيط الإجراء.")
        return mission

    def plan(self, mission: MissionState, *, target: str | None = None) -> MissionState:
        if mission.stage == "action_planned" and mission.action_plan is not None:
            return mission
        if mission.stage != "decide" or not mission.decision:
            raise ValueError("Decision is required before action planning")
        recommended = str(mission.decision.get("recommended_action", ""))
        mission.action_plan = plan_action(recommended, target=target)
        mission.transition("action_planned", "تم إنشاء خطة إجراء منفصلة عن القرار.")
        return mission

    def approve(self, mission: MissionState) -> MissionState:
        if mission.stage == "approved":
            return mission
        if mission.stage != "action_planned" or mission.action_plan is None:
            raise ValueError("Action plan is required before approval")
        if not mission.action_plan.policy.allowed:
            raise PermissionError("Action is blocked by policy")
        mission.action_plan.payload["approved"] = True
        mission.transition("approved", "تم اعتماد الإجراء وفق سياسة NEXUS.")
        return mission

    def execute(self, mission: MissionState) -> MissionState:
        if mission.stage == "executed":
            return mission
        if mission.stage != "approved" or mission.action_plan is None:
            raise ValueError("Approved action plan is required before execution")
        mission.action_result = self._action_executor.execute(mission.action_plan)
        if mission.action_result.status != "completed":
            mission.transition("execution_blocked", "تعذر تنفيذ الإجراء ضمن حدود التنفيذ الحالية.", status=mission.action_result.status)
            return mission
        mission.transition("executed", "تم تنفيذ الإجراء عبر منفذ NEXUS المعتمد.", action_type=mission.action_result.action_type)
        return mission

    def verify(self, mission: MissionState) -> MissionState:
        if mission.stage == "verified":
            return mission
        if mission.stage != "executed" or mission.action_result is None:
            raise ValueError("Successful execution is required before verification")
        mission.verification = self._verifier.verify(mission.action_result)
        target_stage = "verified" if mission.verification.status == "verified" else "verification_failed"
        mission.transition(target_stage, "تمت مراجعة نتيجة التنفيذ والتحقق منها.", status=mission.verification.status)
        return mission

    def complete_demo_execution(self, mission: MissionState) -> MissionState:
        return self.execute(mission)

    def verify_demo(self, mission: MissionState) -> MissionState:
        return self.verify(mission)
