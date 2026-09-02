from __future__ import annotations

# NEXUS mission lifecycle orchestrator. The public plan contract accepts an
# explicit action type/body while preserving the default safe draft-email path.

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable
from uuid import uuid4

from .action_executor import ActionExecutor, ActionResult, draft_email_handler
from .context_builder import build_context
from .goal_planner import Goal, GoalPlan, GoalProfile, ResearchNeed, build_goal_plan, parse_goal
from .impact import ImpactAssessment
from .intelligence_graph import IntelligenceGraph
from .mission_intelligence import MissionIntelligence
from .models import BusinessContext, Entity, Evidence, Relationship, utc_now
from .planner import ActionPlan, plan_action
from .policy import ActionPolicy, ActionRisk
from .research_executor import ResearchExecutor, ResearchResult
from .research_planner import ResearchPlan, ResearchTask, build_research_plan
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
        return {name: _plain(getattr(self, name)) for name in (
            "id", "tenant_id", "goal", "constraints", "stage", "context", "goal_plan",
            "intelligence_graph", "impact_assessments", "research_plan", "research_results",
            "decision", "action_plan", "action_result", "verification", "audit",
        )}


Reasoner = Callable[[str, list[str], BusinessContext], dict[str, Any]]


def _plain(value: Any) -> Any:
    if isinstance(value, Enum): return value.value
    if value is None or isinstance(value, (str, int, float, bool)): return value
    if isinstance(value, dict): return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [_plain(item) for item in value]
    if hasattr(value, "model_dump"): return _plain(value.model_dump(mode="json"))
    if hasattr(value, "__dataclass_fields__"): return {name: _plain(getattr(value, name)) for name in value.__dataclass_fields__}
    return str(value)


def _restore_context(data: dict[str, Any] | None) -> BusinessContext:
    context = BusinessContext(); data = data or {}
    entities = data.get("entities", []); entities = list(entities.values()) if isinstance(entities, dict) else entities
    for item in entities: context.add_entity(Entity(str(item["id"]), str(item["type"]), str(item["name"]), dict(item.get("attributes", {}))))
    evidence_items = data.get("evidence", []); evidence_items = list(evidence_items.values()) if isinstance(evidence_items, dict) else evidence_items
    for item in evidence_items:
        context.add_evidence(Evidence(id=str(item["id"]), source=str(item.get("source", "")), claim=str(item.get("claim", "")), value=item.get("value"), confidence=int(item.get("confidence", 0)), collected_at=str(item.get("collected_at", utc_now())), locator=item.get("locator"), metadata=dict(item.get("metadata", {}))))
    for item in data.get("relationships", []):
        context.link(Relationship(source_id=str(item["source_id"]), relation=str(item["relation"]), target_id=str(item["target_id"]), confidence=int(item.get("confidence", 100)), evidence_ids=list(item.get("evidence_ids", []))))
    return context


def _restore_goal_plan(data: dict[str, Any] | None) -> GoalPlan | None:
    if not data: return None
    goal_data = data.get("goal") or {}; profile_data = data.get("profile") or {}
    goal = Goal(raw=str(goal_data.get("raw", "")), objective=str(goal_data.get("objective", "")), horizon=goal_data.get("horizon"), target_value=goal_data.get("target_value"), target_unit=goal_data.get("target_unit"), constraints=tuple(goal_data.get("constraints", [])))
    profile = GoalProfile(key=str(profile_data.get("key", "general")), label=str(profile_data.get("label", "هدف أعمال عام")), evidence_domains=tuple(profile_data.get("evidence_domains", ())), action_posture=str(profile_data.get("action_posture", "measure_before_action")))
    needs = [ResearchNeed(str(item["domain"]), str(item["reason"]), int(item.get("priority", 50))) for item in data.get("research_needs", [])]
    return GoalPlan(goal=goal, profile=profile, research_needs=needs)


def _restore_research_plan(data: dict[str, Any] | None) -> ResearchPlan | None:
    if not data: return None
    return ResearchPlan(tasks=[ResearchTask(domain=str(item["domain"]), question=str(item["question"]), reason=str(item["reason"]), priority=int(item["priority"]), connector=str(item["connector"]), status=str(item.get("status", "planned"))) for item in data.get("tasks", [])])


def _restore_action_plan(data: dict[str, Any] | None) -> ActionPlan | None:
    if not data: return None
    p = data.get("policy") or {}; policy = ActionPolicy(risk=ActionRisk(str(p.get("risk", "high"))), requires_approval=bool(p.get("requires_approval", True)), allowed=bool(p.get("allowed", False)), reason=str(p.get("reason", "")))
    return ActionPlan(action_type=str(data.get("action_type", "draft_email")), description=str(data.get("description", "")), policy=policy, payload=dict(data.get("payload", {})))


def _restore_action_result(data: dict[str, Any] | None) -> ActionResult | None:
    if not data: return None
    return ActionResult(action_type=str(data.get("action_type", "")), status=str(data.get("status", "")), output=dict(data.get("output", {})), message=str(data.get("message", "")), execution_id=data.get("execution_id"))


def _restore_verification(data: dict[str, Any] | None) -> VerificationResult | None:
    if not data: return None
    return VerificationResult(status=str(data.get("status", "")), checks=list(data.get("checks", [])), details=dict(data.get("details", {})))


def _restore_research_results(data: list[dict[str, Any]]) -> list[ResearchResult]:
    restored = []
    for item in data:
        evidence = [Evidence(id=str(ev["id"]), source=str(ev.get("source", "")), claim=str(ev.get("claim", "")), value=ev.get("value"), confidence=int(ev.get("confidence", 0)), collected_at=str(ev.get("collected_at", utc_now())), locator=ev.get("locator"), metadata=dict(ev.get("metadata", {}))) for ev in item.get("evidence", [])]
        restored.append(ResearchResult(task_domain=str(item.get("task_domain", "")), connector=str(item.get("connector", "")), status=str(item.get("status", "")), evidence=evidence, message=str(item.get("message", ""))))
    return restored


def mission_from_snapshot(snapshot: dict[str, Any]) -> MissionState:
    required = ("id", "tenant_id", "goal", "stage"); missing = [field for field in required if field not in snapshot]
    if missing: raise ValueError(f"Mission snapshot missing fields: {', '.join(missing)}")
    return MissionState(id=str(snapshot["id"]), tenant_id=str(snapshot["tenant_id"]), goal=str(snapshot["goal"]), constraints=[str(item) for item in snapshot.get("constraints", [])], stage=str(snapshot.get("stage", "created")), context=_restore_context(snapshot.get("context")), goal_plan=_restore_goal_plan(snapshot.get("goal_plan")), intelligence_graph=None, impact_assessments=[ImpactAssessment(str(item["key"]), int(item["score"]), bool(item["relevant"]), str(item["reason"])) for item in snapshot.get("impact_assessments", [])], research_plan=_restore_research_plan(snapshot.get("research_plan")), research_results=_restore_research_results(snapshot.get("research_results", [])), decision=dict(snapshot["decision"]) if snapshot.get("decision") is not None else None, action_plan=_restore_action_plan(snapshot.get("action_plan")), action_result=_restore_action_result(snapshot.get("action_result")), verification=_restore_verification(snapshot.get("verification")), audit=list(snapshot.get("audit", [])))


class MissionOrchestrator:
    """Coordinates the NEXUS lifecycle while keeping capabilities replaceable."""

    def __init__(self, reasoner: Reasoner, *, intelligence: MissionIntelligence | None = None, research_executor: ResearchExecutor | None = None, action_executor: ActionExecutor | None = None, verifier: ActionVerifier | None = None) -> None:
        self._reasoner = reasoner; self._intelligence = intelligence or MissionIntelligence(); self._research_executor = research_executor or ResearchExecutor(); self._action_executor = action_executor or ActionExecutor({"draft_email": draft_email_handler}); self._verifier = verifier or ActionVerifier({"draft_email": draft_email_verifier})

    @property
    def action_executor(self) -> ActionExecutor: return self._action_executor
    @property
    def verifier(self) -> ActionVerifier: return self._verifier
    @property
    def research_executor(self) -> ResearchExecutor: return self._research_executor

    def create(self, *, tenant_id: str, goal: str, constraints: Iterable[str] = (), records: Iterable[dict[str, Any]] = (), source: str = "unknown") -> MissionState:
        records = list(records); constraints = list(constraints)
        mission = MissionState(id=f"NXS-{uuid4().hex[:10].upper()}", tenant_id=tenant_id, goal=goal, constraints=constraints)
        mission.transition("observe", "بدأ جمع الإشارات المرتبطة بالمهمة.")
        mission.goal_plan = build_goal_plan(parse_goal(goal, constraints)); mission.context = build_context(records, source=source); mission.intelligence_graph = IntelligenceGraph.from_context(mission.context)
        _, _, assessments = self._intelligence.prepare(tenant_id=tenant_id, goal_text=goal, constraints=constraints, records=records, source=source); mission.impact_assessments = assessments
        mission.research_plan = build_research_plan(mission.goal_plan, mission.context, assessments)
        mission.transition("understand", "تم بناء السياق وخريطة الأدلة وتحديد فجوات المعلومات قبل القرار.", entities=len(mission.context.entities), relationships=len(mission.context.relationships), evidence=len(mission.context.evidence), research_domains=mission.goal_plan.domains() if mission.goal_plan else [], relevant_changes=sum(1 for item in assessments if item.relevant), research_tasks=len(mission.research_plan.pending()) if mission.research_plan else 0)
        return mission

    def research(self, mission: MissionState) -> MissionState:
        if mission.stage not in {"understand", "researched"}: raise ValueError(f"Cannot research from stage: {mission.stage}")
        if mission.research_plan is None: raise ValueError("Research plan is required before execution")
        mission.transition("researching", "يتم جمع الأدلة اللازمة لسد فجوات المعلومات قبل القرار.", task_count=len(mission.research_plan.pending())); mission.research_results = self._research_executor.execute(mission.research_plan, mission.context)
        for result in mission.research_results:
            for evidence in result.evidence: mission.context.add_evidence(evidence)
        mission.transition("researched", "انتهت دورة البحث ويمكن الآن تقييم كفاية الأدلة.", completed=sum(1 for result in mission.research_results if result.status == "completed"), unavailable=sum(1 for result in mission.research_results if result.status == "unavailable"), evidence_added=sum(len(result.evidence) for result in mission.research_results)); return mission

    def decide(self, mission: MissionState) -> MissionState:
        if mission.stage not in {"understand", "researched", "reason"}: raise ValueError(f"Cannot decide from stage: {mission.stage}")
        mission.transition("reason", "يتم تقييم الإشارات والقيود والتغيّرات والأدلة المتاحة."); mission.decision = self._reasoner(mission.goal, mission.constraints, mission.context); mission.transition("decide", "اكتمل القرار وأصبح جاهزًا لتخطيط الإجراء."); return mission

    def plan(self, mission: MissionState, *, target: str | None = None, action_type: str = "draft_email", body: dict[str, Any] | None = None) -> MissionState:
        if mission.stage == "action_planned" and mission.action_plan is not None: return mission
        if mission.stage != "decide" or not mission.decision: raise ValueError("Decision is required before action planning")
        mission.action_plan = plan_action(str(mission.decision.get("recommended_action", "")), target=target, action_type=action_type, body=body)
        mission.transition("action_planned", "تم إنشاء خطة إجراء منفصلة عن القرار."); return mission

    def approve(self, mission: MissionState) -> MissionState:
        if mission.stage == "approved": return mission
        if mission.stage != "action_planned" or mission.action_plan is None: raise ValueError("Action plan is required before approval")
        if not mission.action_plan.policy.allowed: raise PermissionError(mission.action_plan.policy.reason)
        mission.action_plan = ActionPlan(action_type=mission.action_plan.action_type, description=mission.action_plan.description, policy=mission.action_plan.policy, payload={**mission.action_plan.payload, "approved": True})
        mission.transition("approved", "تم اعتماد الإجراء بواسطة المصرّح له."); return mission

    def execute(self, mission: MissionState) -> MissionState:
        if mission.stage in {"executed", "verified"}: return mission
        if mission.stage != "approved" or mission.action_plan is None: raise ValueError("Approved action plan is required before execution")
        mission.action_result = self._action_executor.execute(mission.action_plan)
        if mission.action_result.status != "completed": raise ValueError(mission.action_result.message)
        mission.transition("executed", "تم تنفيذ الإجراء.", execution_id=mission.action_result.execution_id); return mission

    def verify(self, mission: MissionState) -> MissionState:
        if mission.stage == "verified": return mission
        if mission.stage != "executed" or mission.action_result is None: raise ValueError("Executed action is required before verification")
        mission.verification = self._verifier.verify(mission.action_result)
        if mission.verification.status != "verified": raise ValueError("Execution could not be verified")
        mission.transition("verified", "تم التحقق من نتيجة الإجراء.", execution_id=mission.action_result.execution_id); return mission
