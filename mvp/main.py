from __future__ import annotations

import os
import re
from dataclasses import asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from connectors.normalize import normalize_records
from core.auth import ActorRole, AuthenticationError, Principal, authenticate_api_key
from core.models import BusinessContext, Evidence
from core.reasoner import reason_from_evidence
from core.runtime import MissionRuntime, build_runtime
from core.mission_repository import SQLiteMissionRepository

app = FastAPI(title="NEXUS MVP", version="1.0.0", description="Goal-driven AI intelligence: Observe → Understand → Research → Reason → Decide → Act → Verify")

class MissionStatus(str, Enum): ANALYZING="analyzing"; AWAITING_APPROVAL="awaiting_approval"; APPROVED="approved"; EXECUTED="executed"; VERIFIED="verified"
class SourceType(str, Enum): ERP="erp"; CONTRACT="contract"; SUPPLIER="supplier"; MARKET="market"; FILE="file"; CRM="crm"; WEB="web"; UNKNOWN="unknown"
class Signal(BaseModel): id: str; source: SourceType; title: str; value: str; impact: str; confidence: int = Field(ge=0, le=100)
class MissionRequest(BaseModel): goal: str = Field(min_length=5, max_length=500); constraints: list[str] = Field(default_factory=list); action_type: str = Field(default="draft_email", max_length=64); target: str | None = Field(default=None, max_length=500); body: dict[str, Any] = Field(default_factory=dict)
class IngestRequest(BaseModel): filename: str = Field(min_length=1, max_length=255); content: str = Field(min_length=1, max_length=2_000_000)
class ScheduleRequest(BaseModel): connector: str = Field(min_length=1, max_length=64); source: str = Field(min_length=1, max_length=255); interval_seconds: int = Field(ge=60, le=31_536_000); config: dict[str, Any] = Field(default_factory=dict); start_at: datetime | None = None
class Decision(BaseModel): title: str; summary: str; priority: str; confidence: int = Field(ge=0, le=100); rationale: list[str]; recommended_action: str; expected_impact: str; evidence_ids: list[str] = Field(default_factory=list); evidence_count: int = 0; evidence_confidence: int = 0
class AuditEvent(BaseModel): timestamp: str; stage: str; message: str; metadata: dict[str, Any] = Field(default_factory=dict)
class ResearchSummary(BaseModel): domains: list[str] = Field(default_factory=list); completed: int = 0; unavailable: int = 0; evidence_added: int = 0
class Mission(BaseModel): id: str; tenant_id: str; created_at: str; status: MissionStatus; goal: str; constraints: list[str]; sources_used: list[SourceType]; signals: list[Signal]; research: ResearchSummary = Field(default_factory=ResearchSummary); decision: Decision; action: dict[str, Any] | None = None; verification: dict[str, Any] | None = None; audit: list[AuditEvent]

SAMPLE_CONTEXT = {"company":"NEXUS Demo Company","currency":"SAR","suppliers":[{"name":"ABC Industrial","monthly_spend":420000,"price_change":7,"contract_days_left":43},{"name":"Northstar Supply","monthly_spend":180000,"market_delta":-3,"contract_days_left":118}],"operational":{"target_cost_reduction_pct":10,"quality_floor":"unchanged","active_contract_policy":"do_not_break"}}
DEFAULT_TENANT="demo-tenant"; DEFAULT_ROLE=ActorRole.ADMIN; TENANT_PATTERN=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$"); INGESTED_DATA: dict[str,list[dict[str,Any]]]={}; RUNTIME: MissionRuntime=build_runtime(); MISSION_REPOSITORY: SQLiteMissionRepository=RUNTIME.mission_repository

def utc_now(): return datetime.now(timezone.utc).isoformat()
def _strict_auth_enabled(): return os.getenv("NEXUS_AUTH_REQUIRED","false").strip().lower() in {"1","true","yes","on"}
def principal_context(x_api_key: str|None=Header(default=None,alias="X-API-Key"), x_tenant_id: str|None=Header(default=None,alias="X-Tenant-ID"), x_actor_role: str|None=Header(default=None,alias="X-Actor-Role")) -> Principal:
    if _strict_auth_enabled():
        try: principal=authenticate_api_key(x_api_key or "")
        except AuthenticationError as exc: raise HTTPException(401, str(exc)) from exc
        if x_tenant_id and x_tenant_id.strip()!=principal.tenant_id: raise HTTPException(403,"Tenant does not match authenticated principal")
        if x_actor_role and x_actor_role.strip().lower()!=principal.role.value: raise HTTPException(403,"Role does not match authenticated principal")
        return principal
    tenant=(x_tenant_id or DEFAULT_TENANT).strip()
    if not TENANT_PATTERN.fullmatch(tenant): raise HTTPException(400,"Invalid X-Tenant-ID")
    try: role=ActorRole((x_actor_role or DEFAULT_ROLE.value).strip().lower())
    except ValueError as exc: raise HTTPException(400,"Invalid X-Actor-Role") from exc
    return Principal(subject="dev-mode",tenant_id=tenant,role=role)
def tenant_context(principal: Principal=Depends(principal_context)): return principal.tenant_id
def role_context(principal: Principal=Depends(principal_context)): return principal.role
def require_role(role: ActorRole, allowed: set[ActorRole]):
    if role not in allowed: raise HTTPException(403,f"Role '{role.value}' is not authorized for this operation")

def sample_signals():
    return [Signal(id="sig-001",source=SourceType.SUPPLIER,title="Supplier ABC announced a price increase",value="+7% starting next cycle",impact="Raises cost on a high-spend category",confidence=97),Signal(id="sig-002",source=SourceType.ERP,title="ABC represents a large share of monthly spend",value="420,000 SAR / month",impact="Makes the price change financially material",confidence=95),Signal(id="sig-003",source=SourceType.MARKET,title="Market indicator moved in the opposite direction",value="-3% versus the last reference period",impact="Weakens the case for accepting a full +7% increase",confidence=86),Signal(id="sig-004",source=SourceType.CONTRACT,title="Contract permits renegotiation before the increase",value="43 days remaining",impact="Creates a safe intervention window",confidence=94),Signal(id="sig-005",source=SourceType.SUPPLIER,title="Alternative supplier has spare capacity",value="Up to 25% of current volume",impact="Provides negotiation leverage and a fallback",confidence=81)]
def signals_from_ingestion(tenant_id):
    out=[]
    for idx,r in enumerate(INGESTED_DATA.get(tenant_id,[]),1):
        supplier=r.get("supplier","مصدر غير مسمى"); spend=r.get("monthly_spend"); change=r.get("price_change_pct"); days=r.get("contract_days_left")
        if change is not None: out.append(Signal(id=f"file-{idx}-price",source=SourceType.FILE,title=f"تغير سعر مسجل للمورد {supplier}",value=f"{change}%",impact="قد يرفع تكلفة التشغيل",confidence=90))
        if spend is not None: out.append(Signal(id=f"file-{idx}-spend",source=SourceType.FILE,title=f"إنفاق مسجل مع المورد {supplier}",value=f"{spend} SAR / month",impact="يحدد الأثر المالي المحتمل",confidence=88))
        if days is not None: out.append(Signal(id=f"file-{idx}-contract",source=SourceType.FILE,title=f"المدة المتبقية للعقد مع {supplier}",value=f"{days} days",impact="يحدد نافذة التدخل",confidence=86))
    return out
def _context_from_signals(signals):
    c=BusinessContext()
    for s in signals: c.add_evidence(Evidence(id=s.id,source=s.source.value,claim=s.title,value=s.value,confidence=s.confidence,metadata={"impact":s.impact,"kind":"signal"}))
    return c
def reason(goal,constraints,signals): return Decision(**reason_from_evidence(goal,constraints,_context_from_signals(signals)).as_dict())
def _signals_from_core(mission):
    valid={x.value for x in SourceType}; out=[]
    for ev in mission.context.evidence.values():
        src=str(ev.source or "unknown").lower(); out.append(Signal(id=ev.id,source=SourceType(src) if src in valid else SourceType.UNKNOWN,title=str(ev.claim),value=str(ev.value),impact=str((ev.metadata or {}).get("impact","")),confidence=int(ev.confidence)))
    return out
def _status_for_stage(stage): return {"understand":MissionStatus.ANALYZING,"researching":MissionStatus.ANALYZING,"researched":MissionStatus.ANALYZING,"reason":MissionStatus.ANALYZING,"decide":MissionStatus.AWAITING_APPROVAL,"action_planned":MissionStatus.AWAITING_APPROVAL,"approved":MissionStatus.APPROVED,"executed":MissionStatus.EXECUTED,"verified":MissionStatus.VERIFIED}.get(stage,MissionStatus.ANALYZING)
def _decision_from_core(m): return Decision(**(m.decision or {"title":"قرار قيد التحليل","summary":"لم يتم إنتاج قرار بعد.","priority":"medium","confidence":0,"rationale":[],"recommended_action":"","expected_impact":""}))
def _audit_timestamp(m,stage):
    for item in reversed(m.audit):
        if item.get("stage")==stage:return str(item.get("timestamp",""))
    return None
def _audit_actor(p,operation): return {"operation":operation,"actor":{"subject":p.subject,"tenant_id":p.tenant_id,"role":p.role.value}}
def _record_actor_audit(m,p,operation,message): m.log("auth",message,**_audit_actor(p,operation))
def _to_api_mission(m):
    action=None
    if m.action_plan is not None:
        action={"type":m.action_plan.action_type,"status":"approved" if m.stage=="approved" else (m.action_result.status if m.action_result else "planned"),"target":m.action_plan.payload.get("target"),"description":m.action_plan.description,"risk":m.action_plan.policy.risk.value,"approval_required":m.action_plan.policy.requires_approval}
        if m.action_result is not None: action.update(output=m.action_result.output,result_message=m.action_result.message,execution_id=m.action_result.execution_id,executed_at=_audit_timestamp(m,"executed"))
    verification=None
    if m.verification is not None: verification={"status":m.verification.status,"checks":m.verification.checks,"details":m.verification.details,"verified_at":_audit_timestamp(m,"verified"),"execution_id":m.action_result.execution_id if m.action_result else None}
    audit=[AuditEvent(timestamp=str(x.get("timestamp","")),stage=str(x.get("stage","")),message=str(x.get("message","")),metadata=dict(x.get("metadata",{}))) for x in m.audit]; valid={x.value for x in SourceType}; sources={SourceType(str(e.source)) if str(e.source) in valid else SourceType.UNKNOWN for e in m.context.evidence.values()}; completed=sum(1 for x in m.research_results if x.status=="completed"); unavailable=sum(1 for x in m.research_results if x.status=="unavailable"); added=sum(len(x.evidence) for x in m.research_results)
    return Mission(id=m.id,tenant_id=m.tenant_id,created_at=audit[0].timestamp if audit else utc_now(),status=_status_for_stage(m.stage),goal=m.goal,constraints=m.constraints,sources_used=sorted(sources,key=lambda x:x.value),signals=_signals_from_core(m),research=ResearchSummary(domains=m.goal_plan.domains() if m.goal_plan else [],completed=completed,unavailable=unavailable,evidence_added=added),decision=_decision_from_core(m),action=action,verification=verification,audit=audit)
def _save(m): MISSION_REPOSITORY.save(m,updated_at=utc_now()); return _to_api_mission(m)
def _get_core(t,m): return MISSION_REPOSITORY.get(t,m)

@app.get("/health")
def health(): return {"status":"ok","service":"nexus-mvp","version":"1.0.0"}
@app.get("/api/runtime")
def runtime_info(): return {"registry":RUNTIME.registry.describe()}
@app.get("/api/auth/mode")
def auth_mode(): return {"required":_strict_auth_enabled(),"header":"X-API-Key"}
@app.get("/api/context")
def context(tenant_id:str=Depends(tenant_context),role:ActorRole=Depends(role_context)):
    require_role(role,set(ActorRole)); return {**SAMPLE_CONTEXT,"tenant_id":tenant_id,"ingested_records":len(INGESTED_DATA.get(tenant_id,[])),"persisted_missions":len(MISSION_REPOSITORY.list_by_tenant(tenant_id))}
@app.post("/api/ingest/file")
def ingest_file(request:IngestRequest,tenant_id:str=Depends(tenant_context),role:ActorRole=Depends(role_context)):
    require_role(role,{ActorRole.OPERATOR,ActorRole.ADMIN})
    try: result=RUNTIME.registry.connectors["file"].ingest(request.content,filename=request.filename); normalized=normalize_records(result.records)
    except (ValueError,TypeError) as exc: raise HTTPException(400,str(exc)) from exc
    INGESTED_DATA.setdefault(tenant_id,[]).extend(normalized); return {"status":"ingested","tenant_id":tenant_id,"source":result.source,"metadata":{**result.metadata,"normalized":True},"records_added":len(normalized),"total_records":len(INGESTED_DATA[tenant_id])}
@app.get("/api/ingest")
def list_ingested(tenant_id:str=Depends(tenant_context),role:ActorRole=Depends(role_context)):
    require_role(role,set(ActorRole)); records=INGESTED_DATA.get(tenant_id,[]); return {"tenant_id":tenant_id,"count":len(records),"records":records}
@app.post("/api/ingest/schedules")
def create_ingestion_schedule(request:ScheduleRequest,principal:Principal=Depends(principal_context)):
    require_role(principal.role,{ActorRole.OPERATOR,ActorRole.ADMIN})
    if request.connector not in RUNTIME.registry.connectors: raise HTTPException(400,f"Connector '{request.connector}' is not registered")
    try: job=RUNTIME.ingestion_scheduler.register(tenant_id=principal.tenant_id,connector=request.connector,source=request.source,interval_seconds=request.interval_seconds,config=request.config,start_at=request.start_at)
    except ValueError as exc: raise HTTPException(400,str(exc)) from exc
    return job
@app.get("/api/ingest/schedules")
def list_ingestion_schedules(principal:Principal=Depends(principal_context)):
    require_role(principal.role,{ActorRole.VIEWER,ActorRole.OPERATOR,ActorRole.ADMIN}); return RUNTIME.ingestion_scheduler.list(principal.tenant_id)
@app.post("/api/ingest/schedules/run")
def run_ingestion_schedules(principal:Principal=Depends(principal_context)):
    require_role(principal.role,{ActorRole.OPERATOR,ActorRole.ADMIN}); return {"tenant_id":principal.tenant_id,"runs":[asdict(r) for r in RUNTIME.scheduled_ingestion.run_due(principal.tenant_id)]}
@app.post("/api/ingest/schedules/{job_id}/run")
def run_ingestion_schedule(job_id:str,principal:Principal=Depends(principal_context)):
    require_role(principal.role,{ActorRole.OPERATOR,ActorRole.ADMIN}); jobs=[j for j in RUNTIME.ingestion_scheduler.list(principal.tenant_id) if j.id==job_id]
    if not jobs: raise HTTPException(404,"Ingestion job not found")
    return asdict(RUNTIME.scheduled_ingestion.run_job(jobs[0]))
@app.post("/api/ingest/schedules/{job_id}/disable")
def disable_ingestion_schedule(job_id:str,principal:Principal=Depends(principal_context)):
    require_role(principal.role,{ActorRole.OPERATOR,ActorRole.ADMIN})
    if not RUNTIME.ingestion_scheduler.disable(job_id,principal.tenant_id): raise HTTPException(404,"Ingestion job not found")
    return {"status":"disabled","job_id":job_id,"tenant_id":principal.tenant_id}
@app.post("/api/missions",response_model=Mission,status_code=201)
def create_mission(request:MissionRequest,principal:Principal=Depends(principal_context)):
    require_role(principal.role,{ActorRole.OPERATOR,ActorRole.ADMIN}); signals=sample_signals()+signals_from_ingestion(principal.tenant_id); records=[{"supplier":s.title,"monthly_spend":s.value,"impact":s.impact,"source":s.source.value} for s in signals]
    m=RUNTIME.orchestrator.create(tenant_id=principal.tenant_id,goal=request.goal,constraints=request.constraints,records=records,source="api-signals"); RUNTIME.orchestrator.research(m); RUNTIME.orchestrator.decide(m); RUNTIME.orchestrator.plan(m,target=request.target,action_type=request.action_type,body=request.body); _record_actor_audit(m,principal,"create_mission","تم إنشاء المهمة بواسطة هوية مصادقة."); return _save(m)
@app.get("/api/missions",response_model=list[Mission])
def list_missions(tenant_id:str=Depends(tenant_context),role:ActorRole=Depends(role_context)):
    require_role(role,set(ActorRole)); return [_to_api_mission(m) for m in MISSION_REPOSITORY.list_by_tenant(tenant_id)]
@app.get("/api/missions/{mission_id}",response_model=Mission)
def get_mission(mission_id:str,tenant_id:str=Depends(tenant_context),role:ActorRole=Depends(role_context)):
    require_role(role,set(ActorRole)); m=_get_core(tenant_id,mission_id)
    if m is None: raise HTTPException(404,"Mission not found")
    return _to_api_mission(m)
@app.post("/api/missions/{mission_id}/approve",response_model=Mission)
def approve_mission(mission_id:str,principal:Principal=Depends(principal_context)):
    require_role(principal.role,{ActorRole.APPROVER,ActorRole.ADMIN}); m=_get_core(principal.tenant_id,mission_id)
    if m is None: raise HTTPException(404,"Mission not found")
    if m.stage=="approved": return _to_api_mission(m)
    try:
        if m.stage=="decide": RUNTIME.orchestrator.plan(m,target="ABC Industrial")
        RUNTIME.orchestrator.approve(m,actor_subject=principal.subject,actor_role=principal.role.value)
    except PermissionError as exc: raise HTTPException(403,str(exc)) from exc
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc
    _record_actor_audit(m,principal,"approve_mission","تم اعتماد الإجراء بواسطة هوية مصادقة."); return _save(m)
@app.post("/api/missions/{mission_id}/execute",response_model=Mission)
def execute_mission(mission_id:str,principal:Principal=Depends(principal_context)):
    require_role(principal.role,{ActorRole.OPERATOR,ActorRole.ADMIN}); m=_get_core(principal.tenant_id,mission_id)
    if m is None: raise HTTPException(404,"Mission not found")
    if m.stage in {"executed","verified"}: return _to_api_mission(m)
    if m.stage!="approved": raise HTTPException(409,"Mission must be approved before execution")
    try: RUNTIME.orchestrator.execute(m,actor_subject=principal.subject,actor_role=principal.role.value)
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc
    _record_actor_audit(m,principal,"execute_mission","تم تنفيذ الإجراء بواسطة هوية مصادقة."); return _save(m)
@app.post("/api/missions/{mission_id}/verify",response_model=Mission)
def verify_mission(mission_id:str,principal:Principal=Depends(principal_context)):
    require_role(principal.role,{ActorRole.OPERATOR,ActorRole.ADMIN}); m=_get_core(principal.tenant_id,mission_id)
    if m is None: raise HTTPException(404,"Mission not found")
    if m.stage=="verified": return _to_api_mission(m)
    if m.stage!="executed": raise HTTPException(409,"Mission must be executed before verification")
    try: RUNTIME.orchestrator.verify(m)
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc
    _record_actor_audit(m,principal,"verify_mission","تم التحقق من النتيجة بواسطة هوية مصادقة."); return _save(m)
