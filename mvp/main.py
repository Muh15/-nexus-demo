from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from connectors.normalize import normalize_records
from core.models import BusinessContext, Evidence
from core.orchestrator import MissionState
from core.reasoner import reason_from_evidence
from core.runtime import MissionRuntime, build_runtime
from core.mission_repository import SQLiteMissionRepository

app = FastAPI(
    title="NEXUS MVP",
    version="0.9.0",
    description="Goal-driven AI intelligence: Observe → Understand → Research → Reason → Decide → Act → Verify",
)


class MissionStatus(str, Enum):
    ANALYZING = "analyzing"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    EXECUTED = "executed"
    VERIFIED = "verified"


class SourceType(str, Enum):
    ERP = "erp"
    CONTRACT = "contract"
    SUPPLIER = "supplier"
    MARKET = "market"
    FILE = "file"
    CRM = "crm"
    WEB = "web"
    UNKNOWN = "unknown"


class ActorRole(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    APPROVER = "approver"
    ADMIN = "admin"


class Signal(BaseModel):
    id: str
    source: SourceType
    title: str
    value: str
    impact: str
    confidence: int = Field(ge=0, le=100)


class MissionRequest(BaseModel):
    goal: str = Field(min_length=5, max_length=500)
    constraints: list[str] = Field(default_factory=list)


class IngestRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=2_000_000)


class Decision(BaseModel):
    title: str
    summary: str
    priority: str
    confidence: int = Field(ge=0, le=100)
    rationale: list[str]
    recommended_action: str
    expected_impact: str
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_count: int = 0
    evidence_confidence: int = 0


class AuditEvent(BaseModel):
    timestamp: str
    stage: str
    message: str


class ResearchSummary(BaseModel):
    domains: list[str] = Field(default_factory=list)
    completed: int = 0
    unavailable: int = 0
    evidence_added: int = 0


class Mission(BaseModel):
    id: str
    tenant_id: str
    created_at: str
    status: MissionStatus
    goal: str
    constraints: list[str]
    sources_used: list[SourceType]
    signals: list[Signal]
    research: ResearchSummary = Field(default_factory=ResearchSummary)
    decision: Decision
    action: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    audit: list[AuditEvent]


SAMPLE_CONTEXT: dict[str, Any] = {
    "company": "NEXUS Demo Company",
    "currency": "SAR",
    "suppliers": [
        {"name": "ABC Industrial", "monthly_spend": 420000, "price_change": 7, "contract_days_left": 43},
        {"name": "Northstar Supply", "monthly_spend": 180000, "market_delta": -3, "contract_days_left": 118},
    ],
    "operational": {
        "target_cost_reduction_pct": 10,
        "quality_floor": "unchanged",
        "active_contract_policy": "do_not_break",
    },
}

DEFAULT_TENANT = "demo-tenant"
DEFAULT_ROLE = ActorRole.ADMIN
TENANT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
INGESTED_DATA: dict[str, list[dict[str, Any]]] = {}
RUNTIME: MissionRuntime = build_runtime()
MISSION_REPOSITORY: SQLiteMissionRepository = RUNTIME.mission_repository


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def tenant_context(x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID")) -> str:
    tenant_id = (x_tenant_id or DEFAULT_TENANT).strip()
    if not TENANT_PATTERN.fullmatch(tenant_id):
        raise HTTPException(status_code=400, detail="Invalid X-Tenant-ID")
    return tenant_id


def role_context(x_actor_role: str | None = Header(default=None, alias="X-Actor-Role")) -> ActorRole:
    value = (x_actor_role or DEFAULT_ROLE.value).strip().lower()
    try:
        return ActorRole(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid X-Actor-Role") from exc


def require_role(role: ActorRole, allowed: set[ActorRole]) -> None:
    if role not in allowed:
        raise HTTPException(status_code=403, detail=f"Role '{role.value}' is not authorized for this operation")


def sample_signals() -> list[Signal]:
    return [
        Signal(id="sig-001", source=SourceType.SUPPLIER, title="Supplier ABC announced a price increase", value="+7% starting next cycle", impact="Raises cost on a high-spend category", confidence=97),
        Signal(id="sig-002", source=SourceType.ERP, title="ABC represents a large share of monthly spend", value="420,000 SAR / month", impact="Makes the price change financially material", confidence=95),
        Signal(id="sig-003", source=SourceType.MARKET, title="Market indicator moved in the opposite direction", value="-3% versus the last reference period", impact="Weakens the case for accepting a full +7% increase", confidence=86),
        Signal(id="sig-004", source=SourceType.CONTRACT, title="Contract permits renegotiation before the increase", value="43 days remaining", impact="Creates a safe intervention window", confidence=94),
        Signal(id="sig-005", source=SourceType.SUPPLIER, title="Alternative supplier has spare capacity", value="Up to 25% of current volume", impact="Provides negotiation leverage and a fallback", confidence=81),
    ]


def signals_from_ingestion(tenant_id: str) -> list[Signal]:
    signals: list[Signal] = []
    for idx, record in enumerate(INGESTED_DATA.get(tenant_id, []), start=1):
        supplier = record.get("supplier", "مصدر غير مسمى")
        spend = record.get("monthly_spend")
        change = record.get("price_change_pct")
        days = record.get("contract_days_left")
        if change is not None:
            signals.append(Signal(id=f"file-{idx}-price", source=SourceType.FILE, title=f"تغير سعر مسجل للمورد {supplier}", value=f"{change}%", impact="قد يرفع تكلفة التشغيل", confidence=90))
        if spend is not None:
            signals.append(Signal(id=f"file-{idx}-spend", source=SourceType.FILE, title=f"إنفاق مسجل مع المورد {supplier}", value=f"{spend} SAR / month", impact="يحدد الأثر المالي المحتمل", confidence=88))
        if days is not None:
            signals.append(Signal(id=f"file-{idx}-contract", source=SourceType.FILE, title=f"المدة المتبقية للعقد مع {supplier}", value=f"{days} days", impact="يحدد نافذة التدخل", confidence=86))
    return signals


def _context_from_signals(signals: list[Signal]) -> BusinessContext:
    context = BusinessContext()
    for signal in signals:
        context.add_evidence(Evidence(id=signal.id, source=signal.source.value, claim=signal.title, value=signal.value, confidence=signal.confidence, metadata={"impact": signal.impact, "kind": "signal"}))
    return context


def reason(goal: str, constraints: list[str], signals: list[Signal]) -> Decision:
    decision = reason_from_evidence(goal, constraints, _context_from_signals(signals))
    return Decision(**decision.as_dict())


def _signals_from_core(mission: MissionState) -> list[Signal]:
    result: list[Signal] = []
    valid_sources = {item.value for item in SourceType}
    for evidence in mission.context.evidence.values():
        raw_source = str(evidence.source or "unknown").lower()
        source = SourceType(raw_source) if raw_source in valid_sources else SourceType.UNKNOWN
        metadata = evidence.metadata or {}
        result.append(Signal(id=evidence.id, source=source, title=str(evidence.claim), value=str(evidence.value), impact=str(metadata.get("impact", "")), confidence=int(evidence.confidence)))
    return result


def _status_for_stage(stage: str) -> MissionStatus:
    return {"understand": MissionStatus.ANALYZING, "researching": MissionStatus.ANALYZING, "researched": MissionStatus.ANALYZING, "reason": MissionStatus.ANALYZING, "decide": MissionStatus.AWAITING_APPROVAL, "action_planned": MissionStatus.AWAITING_APPROVAL, "approved": MissionStatus.APPROVED, "executed": MissionStatus.EXECUTED, "verified": MissionStatus.VERIFIED}.get(stage, MissionStatus.ANALYZING)


def _decision_from_core(mission: MissionState) -> Decision:
    return Decision(**(mission.decision or {"title": "قرار قيد التحليل", "summary": "لم يتم إنتاج قرار بعد.", "priority": "medium", "confidence": 0, "rationale": [], "recommended_action": "", "expected_impact": ""}))


def _audit_timestamp(mission: MissionState, stage: str) -> str | None:
    for item in reversed(mission.audit):
        if item.get("stage") == stage:
            return str(item.get("timestamp", ""))
    return None


def _to_api_mission(mission: MissionState) -> Mission:
    decision = _decision_from_core(mission)
    completed = sum(1 for item in mission.research_results if item.status == "completed")
    unavailable = sum(1 for item in mission.research_results if item.status == "unavailable")
    evidence_added = sum(len(item.evidence) for item in mission.research_results)
    action: dict[str, Any] | None = None
    if mission.action_plan is not None:
        action = {
            "type": mission.action_plan.action_type,
            "status": "approved" if mission.stage == "approved" else (mission.action_result.status if mission.action_result else "planned"),
            "target": mission.action_plan.payload.get("target"),
            "description": mission.action_plan.description,
            "risk": mission.action_plan.policy.risk.value,
            "approval_required": mission.action_plan.policy.requires_approval,
        }
        if mission.action_result is not None:
            action["output"] = mission.action_result.output
            action["result_message"] = mission.action_result.message
            action["execution_id"] = mission.action_result.execution_id
            action["executed_at"] = _audit_timestamp(mission, "executed")
    verification = None
    if mission.verification is not None:
        verification = {
            "status": mission.verification.status,
            "checks": mission.verification.checks,
            "details": mission.verification.details,
            "verified_at": _audit_timestamp(mission, "verified"),
            "execution_id": mission.action_result.execution_id if mission.action_result else None,
        }
    audit = [AuditEvent(timestamp=str(item.get("timestamp", "")), stage=str(item.get("stage", "")), message=str(item.get("message", ""))) for item in mission.audit]
    valid_sources = {item.value for item in SourceType}
    sources = {SourceType(str(ev.source)) if str(ev.source) in valid_sources else SourceType.UNKNOWN for ev in mission.context.evidence.values()}
    return Mission(id=mission.id, tenant_id=mission.tenant_id, created_at=audit[0].timestamp if audit else utc_now(), status=_status_for_stage(mission.stage), goal=mission.goal, constraints=mission.constraints, sources_used=sorted(sources, key=lambda value: value.value), signals=_signals_from_core(mission), research=ResearchSummary(domains=mission.goal_plan.domains() if mission.goal_plan else [], completed=completed, unavailable=unavailable, evidence_added=evidence_added), decision=decision, action=action, verification=verification, audit=audit)


def _save(mission: MissionState) -> Mission:
    MISSION_REPOSITORY.save(mission, updated_at=utc_now())
    return _to_api_mission(mission)


def _get_core(tenant_id: str, mission_id: str) -> MissionState | None:
    return MISSION_REPOSITORY.get(tenant_id, mission_id)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "nexus-mvp", "version": "0.9.0"}


@app.get("/api/runtime")
def runtime_info() -> dict[str, Any]:
    return {"registry": RUNTIME.registry.describe()}


@app.get("/api/context")
def context(tenant_id: str = Depends(tenant_context), role: ActorRole = Depends(role_context)) -> dict[str, Any]:
    require_role(role, {ActorRole.VIEWER, ActorRole.OPERATOR, ActorRole.APPROVER, ActorRole.ADMIN})
    return {**SAMPLE_CONTEXT, "tenant_id": tenant_id, "ingested_records": len(INGESTED_DATA.get(tenant_id, [])), "persisted_missions": len(MISSION_REPOSITORY.list_by_tenant(tenant_id))}


@app.post("/api/ingest/file")
def ingest_file(request: IngestRequest, tenant_id: str = Depends(tenant_context), role: ActorRole = Depends(role_context)) -> dict[str, Any]:
    require_role(role, {ActorRole.OPERATOR, ActorRole.ADMIN})
    connector = RUNTIME.registry.connectors["file"]
    try:
        result = connector.ingest(request.content, filename=request.filename)
        normalized = normalize_records(result.records)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    INGESTED_DATA.setdefault(tenant_id, []).extend(normalized)
    return {"status": "ingested", "tenant_id": tenant_id, "source": result.source, "metadata": {**result.metadata, "normalized": True}, "records_added": len(normalized), "total_records": len(INGESTED_DATA[tenant_id])}


@app.get("/api/ingest")
def list_ingested(tenant_id: str = Depends(tenant_context), role: ActorRole = Depends(role_context)) -> dict[str, Any]:
    require_role(role, {ActorRole.VIEWER, ActorRole.OPERATOR, ActorRole.APPROVER, ActorRole.ADMIN})
    records = INGESTED_DATA.get(tenant_id, [])
    return {"tenant_id": tenant_id, "count": len(records), "records": records}


@app.post("/api/missions", response_model=Mission, status_code=201)
def create_mission(request: MissionRequest, tenant_id: str = Depends(tenant_context), role: ActorRole = Depends(role_context)) -> Mission:
    require_role(role, {ActorRole.OPERATOR, ActorRole.ADMIN})
    signals = sample_signals() + signals_from_ingestion(tenant_id)
    records = [{"supplier": signal.title, "monthly_spend": signal.value, "impact": signal.impact, "source": signal.source.value} for signal in signals]
    mission = RUNTIME.orchestrator.create(tenant_id=tenant_id, goal=request.goal, constraints=request.constraints, records=records, source="api-signals")
    RUNTIME.orchestrator.research(mission)
    RUNTIME.orchestrator.decide(mission)
    return _save(mission)


@app.get("/api/missions", response_model=list[Mission])
def list_missions(tenant_id: str = Depends(tenant_context), role: ActorRole = Depends(role_context)) -> list[Mission]:
    require_role(role, {ActorRole.VIEWER, ActorRole.OPERATOR, ActorRole.APPROVER, ActorRole.ADMIN})
    return [_to_api_mission(mission) for mission in MISSION_REPOSITORY.list_by_tenant(tenant_id)]


@app.get("/api/missions/{mission_id}", response_model=Mission)
def get_mission(mission_id: str, tenant_id: str = Depends(tenant_context), role: ActorRole = Depends(role_context)) -> Mission:
    require_role(role, {ActorRole.VIEWER, ActorRole.OPERATOR, ActorRole.APPROVER, ActorRole.ADMIN})
    mission = _get_core(tenant_id, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return _to_api_mission(mission)


@app.post("/api/missions/{mission_id}/approve", response_model=Mission)
def approve_mission(mission_id: str, tenant_id: str = Depends(tenant_context), role: ActorRole = Depends(role_context)) -> Mission:
    require_role(role, {ActorRole.APPROVER, ActorRole.ADMIN})
    mission = _get_core(tenant_id, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission.stage == "approved":
        return _to_api_mission(mission)
    try:
        if mission.stage == "decide":
            RUNTIME.orchestrator.plan(mission, target="ABC Industrial")
        RUNTIME.orchestrator.approve(mission)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _save(mission)


@app.post("/api/missions/{mission_id}/execute", response_model=Mission)
def execute_mission(mission_id: str, tenant_id: str = Depends(tenant_context), role: ActorRole = Depends(role_context)) -> Mission:
    require_role(role, {ActorRole.OPERATOR, ActorRole.ADMIN})
    mission = _get_core(tenant_id, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission.stage in {"executed", "verified"}:
        return _to_api_mission(mission)
    if mission.stage != "approved":
        raise HTTPException(status_code=409, detail="Mission must be approved before execution")
    result = RUNTIME.orchestrator.execute(mission)
    if result.stage != "executed":
        raise HTTPException(status_code=409, detail=mission.action_result.message if mission.action_result else "Execution failed")
    return _save(mission)


@app.post("/api/missions/{mission_id}/verify", response_model=Mission)
def verify_mission(mission_id: str, tenant_id: str = Depends(tenant_context), role: ActorRole = Depends(role_context)) -> Mission:
    require_role(role, {ActorRole.OPERATOR, ActorRole.ADMIN})
    mission = _get_core(tenant_id, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission.stage == "verified":
        return _to_api_mission(mission)
    if mission.stage != "executed":
        raise HTTPException(status_code=409, detail="Mission must be executed before verification")
    result = RUNTIME.orchestrator.verify(mission)
    if result.stage != "verified":
        raise HTTPException(status_code=409, detail="Execution could not be verified")
    return _save(mission)
