from __future__ import annotations
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
    id:str; tenant_id:str; goal:str; constraints:list[str]=field(default_factory=list); stage:str="created"; context:BusinessContext=field(default_factory=BusinessContext); goal_plan:GoalPlan|None=None; intelligence_graph:IntelligenceGraph|None=None; impact_assessments:list[ImpactAssessment]=field(default_factory=list); research_plan:ResearchPlan|None=None; research_results:list[ResearchResult]=field(default_factory=list); decision:dict[str,Any]|None=None; action_plan:ActionPlan|None=None; action_result:ActionResult|None=None; verification:VerificationResult|None=None; audit:list[dict[str,Any]]=field(default_factory=list)
    def log(self,stage,message,**metadata):self.audit.append({"timestamp":utc_now(),"stage":stage,"message":message,"metadata":metadata})
    def transition(self,stage,message,**metadata):self.stage=stage;self.log(stage,message,**metadata)
    def snapshot(self):return {n:_plain(getattr(self,n)) for n in ("id","tenant_id","goal","constraints","stage","context","goal_plan","intelligence_graph","impact_assessments","research_plan","research_results","decision","action_plan","action_result","verification","audit")}
Reasoner=Callable[[str,list[str],BusinessContext],dict[str,Any]]
def _plain(v):
    if isinstance(v,Enum):return v.value
    if v is None or isinstance(v,(str,int,float,bool)):return v
    if isinstance(v,dict):return {str(k):_plain(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [_plain(x) for x in v]
    if hasattr(v,"model_dump"):return _plain(v.model_dump(mode="json"))
    if hasattr(v,"__dataclass_fields__"):return {n:_plain(getattr(v,n)) for n in v.__dataclass_fields__}
    return str(v)
def _restore_context(d):
    c=BusinessContext();d=d or {};es=d.get("evidence",[]);es=list(es.values()) if isinstance(es,dict) else es
    entities=d.get("entities",[]);entities=list(entities.values()) if isinstance(entities,dict) else entities
    for x in entities:c.add_entity(Entity(str(x["id"]),str(x["type"]),str(x["name"]),dict(x.get("attributes",{}))))
    for x in es:c.add_evidence(Evidence(id=str(x["id"]),source=str(x.get("source","")),claim=str(x.get("claim","")),value=x.get("value"),confidence=int(x.get("confidence",0)),collected_at=str(x.get("collected_at",utc_now())),locator=x.get("locator"),metadata=dict(x.get("metadata",{}))))
    for x in d.get("relationships",[]):c.link(Relationship(source_id=str(x["source_id"]),relation=str(x["relation"]),target_id=str(x["target_id"]),confidence=int(x.get("confidence",100)),evidence_ids=list(x.get("evidence_ids",[]))))
    return c
def _restore_goal_plan(d):
    if not d:return None
    g=d.get("goal") or {};p=d.get("profile") or {};return GoalPlan(Goal(raw=str(g.get("raw","")),objective=str(g.get("objective","")),horizon=g.get("horizon"),target_value=g.get("target_value"),target_unit=g.get("target_unit"),constraints=tuple(g.get("constraints",[]))),GoalProfile(key=str(p.get("key","general")),label=str(p.get("label","هدف أعمال عام")),evidence_domains=tuple(p.get("evidence_domains",())),action_posture=str(p.get("action_posture","measure_before_action"))),[ResearchNeed(str(x["domain"]),str(x["reason"]),int(x.get("priority",50))) for x in d.get("research_needs",[])])
def _restore_research_plan(d):
    if not d:return None
    return ResearchPlan(tasks=[ResearchTask(domain=str(x["domain"]),question=str(x["question"]),reason=str(x["reason"]),priority=int(x["priority"]),connector=str(x["connector"]),status=str(x.get("status","planned"))) for x in d.get("tasks",[])])
def _restore_research_results(data):
    out=[]
    for item in data or []:
        evidence=[Evidence(id=str(x["id"]),source=str(x.get("source","")),claim=str(x.get("claim","")),value=x.get("value"),confidence=int(x.get("confidence",0)),collected_at=str(x.get("collected_at",utc_now())),locator=x.get("locator"),metadata=dict(x.get("metadata",{}))) for x in item.get("evidence",[])]
        out.append(ResearchResult(task_domain=str(item.get("task_domain","")),connector=str(item.get("connector","")),status=str(item.get("status","")),evidence=evidence,message=str(item.get("message",""))))
    return out
def _restore_action_plan(d):
    if not d:return None
    p=d.get("policy") or {};return ActionPlan(str(d.get("action_type","draft_email")),str(d.get("description","")),ActionPolicy(ActionRisk(str(p.get("risk","high"))),bool(p.get("requires_approval",True)),bool(p.get("allowed",False)),str(p.get("reason",""))),dict(d.get("payload",{})))
def _restore_action_result(d):
    if not d:return None
    return ActionResult(str(d.get("action_type","")),str(d.get("status","")),dict(d.get("output",{})),str(d.get("message","")),d.get("execution_id"))
def _restore_verification(d):
    if not d:return None
    return VerificationResult(str(d.get("status","")),list(d.get("checks",[])),dict(d.get("details",{})))
def mission_from_snapshot(s):
    missing=[x for x in ("id","tenant_id","goal","stage") if x not in s]
    if missing:raise ValueError(f"Mission snapshot missing fields: {', '.join(missing)}")
    return MissionState(id=str(s["id"]),tenant_id=str(s["tenant_id"]),goal=str(s["goal"]),constraints=[str(x) for x in s.get("constraints",[])],stage=str(s.get("stage","created")),context=_restore_context(s.get("context")),goal_plan=_restore_goal_plan(s.get("goal_plan")),intelligence_graph=None,impact_assessments=[ImpactAssessment(str(x["key"]),int(x["score"]),bool(x["relevant"]),str(x["reason"])) for x in s.get("impact_assessments",[])],research_plan=_restore_research_plan(s.get("research_plan")),research_results=_restore_research_results(s.get("research_results",[])),decision=dict(s["decision"]) if s.get("decision") is not None else None,action_plan=_restore_action_plan(s.get("action_plan")),action_result=_restore_action_result(s.get("action_result")),verification=_restore_verification(s.get("verification")),audit=list(s.get("audit",[])))
class MissionOrchestrator:
    def __init__(self,reasoner:Reasoner,*,intelligence=None,research_executor=None,action_executor=None,verifier=None):self._reasoner=reasoner;self._intelligence=intelligence or MissionIntelligence();self._research_executor=research_executor or ResearchExecutor();self._action_executor=action_executor or ActionExecutor({"draft_email":draft_email_handler});self._verifier=verifier or ActionVerifier({"draft_email":draft_email_verifier})
    @property
    def action_executor(self):return self._action_executor
    @property
    def verifier(self):return self._verifier
    @property
    def research_executor(self):return self._research_executor
    def create(self,*,tenant_id,goal,constraints=(),records=(),source="unknown"):
        m=MissionState(f"NXS-{uuid4().hex[:10].upper()}",tenant_id,goal,list(constraints));records=list(records);m.transition("observe","بدأ جمع الإشارات المرتبطة بالمهمة.");m.goal_plan=build_goal_plan(parse_goal(goal,m.constraints));m.context=build_context(records,source=source);m.intelligence_graph=IntelligenceGraph.from_context(m.context);_,_,m.impact_assessments=self._intelligence.prepare(tenant_id=tenant_id,goal_text=goal,constraints=m.constraints,records=records,source=source);m.research_plan=build_research_plan(m.goal_plan,m.context,m.impact_assessments);m.transition("understand","تم بناء السياق وخريطة الأدلة وتحديد فجوات المعلومات قبل القرار.");return m
    def research(self,m):
        if m.stage not in {"understand","researched"}:raise ValueError(f"Cannot research from stage: {m.stage}")
        m.transition("researching","يتم جمع الأدلة اللازمة لسد فجوات المعلومات قبل القرار.");m.research_results=self._research_executor.execute(m.research_plan,m.context)
        for r in m.research_results:
            for e in r.evidence:m.context.add_evidence(e)
        m.transition("researched","انتهت دورة البحث ويمكن الآن تقييم كفاية الأدلة قبل القرار.");return m
    def decide(self,m):
        if m.stage not in {"understand","researched","reason"}:raise ValueError(f"Cannot decide from stage: {m.stage}")
        m.transition("reason","يتم تقييم الإشارات والقيود والتغيّرات والأدلة المتاحة.");m.decision=self._reasoner(m.goal,m.constraints,m.context);m.transition("decide","اكتمل القرار وأصبح جاهزًا لتخطيط الإجراء.");return m
    def plan(self,m,*,target=None,action_type="draft_email",body=None):
        if m.stage=="action_planned" and m.action_plan:return m
        if m.stage!="decide" or not m.decision:raise ValueError("Decision is required before action planning")
        m.action_plan=plan_action(str(m.decision.get("recommended_action","")),target=target,action_type=action_type,body=body);m.transition("action_planned","تم إنشاء خطة إجراء منفصلة عن القرار.");return m
    def approve(self,m):
        if m.stage=="approved":return m
        if m.stage!="action_planned" or not m.action_plan:raise ValueError("Action plan is required before approval")
        if not m.action_plan.policy.allowed:raise PermissionError(m.action_plan.policy.reason)
        m.action_plan=ActionPlan(m.action_plan.action_type,m.action_plan.description,m.action_plan.policy,{**m.action_plan.payload,"approved":True});m.transition("approved","تم اعتماد الإجراء بواسطة المصرّح له.");return m
    def execute(self,m):
        if m.stage in {"executed","verified"}:return m
        if m.stage!="approved" or not m.action_plan:raise ValueError("Approved action plan is required before execution")
        m.action_result=self._action_executor.execute(m.action_plan)
        if m.action_result.status!="completed":raise ValueError(m.action_result.message)
        m.transition("executed","تم تنفيذ الإجراء.",execution_id=m.action_result.execution_id);return m
    def complete_demo_execution(self,m):return self.execute(m)
    def verify(self,m):
        if m.stage=="verified":return m
        if m.stage!="executed" or not m.action_result:raise ValueError("Executed action is required before verification")
        m.verification=self._verifier.verify(m.action_result)
        if m.verification.status!="verified":raise ValueError("Execution could not be verified")
        m.transition("verified","تم التحقق من نتيجة الإجراء.",execution_id=m.action_result.execution_id);return m
