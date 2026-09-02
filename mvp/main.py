from __future__ import annotations

import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from connectors.file_connector import FileConnector
from connectors.normalize import normalize_records
from core.action_executor import ActionExecutor, draft_email_handler
from core.models import BusinessContext, Evidence
from core.orchestrator import MissionOrchestrator
from core.planner import plan_action
from core.reasoner import reason_from_evidence
from core.research_executor import ResearchExecutor, context_provider
from core.sqlite_store import SQLiteMissionStore
from core.verifier import ActionVerifier, draft_email_verifier

app = FastAPI(
    title="NEXUS MVP",
    version="0.5.0",
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

INGESTED_DATA: list[dict[str, Any]] = []
MISSION_DB_PATH = os.getenv("NEXUS_DB_PATH", "nexus_mvp.sqlite3")
MISSION_STORE = SQLiteMissionStore(MISSION_DB_PATH)
MISSIONS: dict[str, Mission] = {}
ACTION_EXECUTOR = ActionExecutor({"draft_email": draft_email_handler})
ACTION_VERIFIER = ActionVerifier({"draft_email": draft_email_verifier})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sample_signals() -> list[Signal]:
    return [
        Signal(id="sig-001", source=SourceType.SUPPLIER, title="Supplier ABC announced a price increase", value="+7% starting next cycle", impact="Raises cost on a high-spend category", confidence=97),
        Signal(id="sig-002", source=SourceType.ERP, title="ABC represents a large share of monthly spend", value="420,000 SAR / month", impact="Makes the price change financially material", confidence=95),
        Signal(id="sig-003", source=SourceType.MARKET, title="Market indicator moved in the opposite direction", value="-3% versus the last reference period", impact="Weakens the case for accepting a full +7% increase", confidence=86),
        Signal(id="sig-004", source=SourceType.CONTRACT, title="Contract permits renegotiation before the increase", value="43 days remaining", impact="Creates a safe intervention window", confidence=94),
        Signal(id="sig-005", source=SourceType.SUPPLIER, title="Alternative supplier has spare capacity", value="Up to 25% of current volume", impact="Provides negotiation leverage and a fallback", confidence=81),
    ]


def signals_from_ingestion() -> list[Signal]:
    signals: list[Signal] = []
    for idx, record in enumerate(INGESTED_DATA, start=1):
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


def log_event(audit: list[AuditEvent], stage: str, message: str) -> None:
    audit.append(AuditEvent(timestamp=utc_now(), stage=stage, message=message))


def _context_from_signals(signals: list[Signal]) -> BusinessContext:
    context = BusinessContext()
    for signal in signals:
        context.add_evidence(Evidence(id=signal.id, source=signal.source.value, claim=signal.title, value=signal.value, confidence=signal.confidence, metadata={"impact": signal.impact, "kind": "signal"}))
    return context


def reason(goal: str, constraints: list[str], signals: list[Signal]) -> Decision:
    decision = reason_from_evidence(goal, constraints, _context_from_signals(signals))
    return Decision(**decision.as_dict())


def _research_executor() -> ResearchExecutor:
    executor = ResearchExecutor()
    for connector, source in {"file": "file", "supplier": "supplier_connector", "erp": "erp_connector", "contract": "contract_connector", "market": "market_connector", "crm": "crm_connector", "web": "web_connector"}.items():
        executor.register(connector, context_provider(connector, source, confidence=82))
    return executor


def _run_mission(goal: str, constraints: list[str], signals: list[Signal]):
    records = [{"supplier": signal.title, "monthly_spend": signal.value, "impact": signal.impact, "source": signal.source.value} for signal in signals]
    orchestrator = MissionOrchestrator(lambda mission_goal, mission_constraints, context: reason_from_evidence(mission_goal, mission_constraints, context).as_dict(), research_executor=_research_executor())
    mission = orchestrator.create(tenant_id="demo-tenant", goal=goal, constraints=constraints, records=records, source="api-signals")
    orchestrator.research(mission)
    orchestrator.decide(mission)
    return mission


def _persist_mission(mission: Mission) -> Mission:
    MISSIONS[mission.id] = mission
    MISSION_STORE.save(mission.id, mission.model_dump(mode="json"), utc_now())
    return mission


def _load_mission(mission_id: str) -> Mission | None:
    cached = MISSIONS.get(mission_id)
    if cached is not None:
        return cached
    payload = MISSION_STORE.get(mission_id)
    if payload is None:
        return None
    mission = Mission.model_validate(payload)
    MISSIONS[mission.id] = mission
    return mission


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "nexus-mvp", "version": "0.5.0"}


@app.get("/api/context")
def context() -> dict[str, Any]:
    return {**SAMPLE_CONTEXT, "ingested_records": len(INGESTED_DATA), "persisted_missions": len(MISSION_STORE.list_ids())}


@app.post("/api/ingest/file")
def ingest_file(request: IngestRequest) -> dict[str, Any]:
    connector = FileConnector()
    try:
        result = connector.ingest(request.content, filename=request.filename)
        normalized = normalize_records(result.records)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    INGESTED_DATA.extend(normalized)
    return {"status": "ingested", "source": result.source, "metadata": {**result.metadata, "normalized": True}, "records_added": len(normalized), "total_records": len(INGESTED_DATA)}


@app.get("/api/ingest")
def list_ingested() -> dict[str, Any]:
    return {"count": len(INGESTED_DATA), "records": INGESTED_DATA}


@app.post("/api/missions", response_model=Mission, status_code=201)
def create_mission(request: MissionRequest) -> Mission:
    mission_id = f"NXS-{uuid4().hex[:10].upper()}"
    audit: list[AuditEvent] = []
    log_event(audit, "mission", "تم استلام المهمة وفهم الهدف والقيود.")
    signals = sample_signals() + signals_from_ingestion()
    log_event(audit, "observe", "تم جمع الإشارات من المصادر الحالية.")
    core_mission = _run_mission(request.goal, request.constraints, signals)
    log_event(audit, "understand", f"تم بناء السياق وتحديد {len(core_mission.research_plan.pending()) if core_mission.research_plan else 0} فجوات بحث.")
    log_event(audit, "research", "تم تنفيذ خطة البحث وجمع الأدلة المتاحة قبل القرار.")
    decision = Decision(**(core_mission.decision or {}))
    completed = sum(1 for result in core_mission.research_results if result.status == "completed")
    unavailable = sum(1 for result in core_mission.research_results if result.status == "unavailable")
    evidence_added = sum(len(result.evidence) for result in core_mission.research_results)
    research_domains = core_mission.goal_plan.domains() if core_mission.goal_plan else []
    log_event(audit, "reason", "تم تقييم الأدلة والقيود لإنتاج قرار مبني على ما تم جمعه.")
    log_event(audit, "decide", f"القرار جاهز للاعتماد بثقة {decision.confidence}% من {decision.evidence_count} دليل.")
    mission = Mission(id=mission_id, created_at=utc_now(), status=MissionStatus.AWAITING_APPROVAL, goal=request.goal, constraints=request.constraints, sources_used=sorted(set(s.source for s in signals), key=lambda x: x.value), signals=signals, research=ResearchSummary(domains=research_domains, completed=completed, unavailable=unavailable, evidence_added=evidence_added), decision=decision, audit=audit)
    return _persist_mission(mission)


@app.get("/api/missions", response_model=list[Mission])
def list_missions() -> list[Mission]:
    missions: list[Mission] = []
    for mission_id in MISSION_STORE.list_ids():
        mission = _load_mission(mission_id)
        if mission is not None:
            missions.append(mission)
    return missions


@app.get("/api/missions/{mission_id}", response_model=Mission)
def get_mission(mission_id: str) -> Mission:
    mission = _load_mission(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission


@app.post("/api/missions/{mission_id}/approve", response_model=Mission)
def approve_mission(mission_id: str) -> Mission:
    mission = get_mission(mission_id)
    if mission.status != MissionStatus.AWAITING_APPROVAL:
        raise HTTPException(status_code=409, detail="Mission is not awaiting approval")
    action_plan = plan_action(mission.decision.recommended_action, target="ABC Industrial")
    if not action_plan.policy.allowed:
        raise HTTPException(status_code=403, detail=action_plan.policy.reason)
    action_plan.payload["approved"] = True
    mission.status = MissionStatus.APPROVED
    mission.action = {"type": action_plan.action_type, "status": "approved", "target": action_plan.payload.get("target"), "description": action_plan.description, "risk": action_plan.policy.risk.value, "approval_required": action_plan.policy.requires_approval}
    log_event(mission.audit, "approve", "تم اعتماد خطة الإجراء بعد فحص سياسة NEXUS.")
    return _persist_mission(mission)


@app.post("/api/missions/{mission_id}/execute", response_model=Mission)
def execute_mission(mission_id: str) -> Mission:
    mission = get_mission(mission_id)
    if mission.status != MissionStatus.APPROVED:
        raise HTTPException(status_code=409, detail="Mission must be approved before execution")
    action_plan = plan_action(mission.decision.recommended_action, target=(mission.action or {}).get("target"))
    action_plan.payload["approved"] = True
    result = ACTION_EXECUTOR.execute(action_plan)
    if result.status != "completed":
        raise HTTPException(status_code=409, detail=result.message or result.status)
    mission.action = {**(mission.action or {}), "status": "executed", "output": result.output, "result_message": result.message, "executed_at": utc_now()}
    mission.status = MissionStatus.EXECUTED
    log_event(mission.audit, "act", "تم تنفيذ الإجراء عبر ActionExecutor المعتمد؛ لم يتم إرسال بريد خارجي.")
    return _persist_mission(mission)


@app.post("/api/missions/{mission_id}/verify", response_model=Mission)
def verify_mission(mission_id: str) -> Mission:
    mission = get_mission(mission_id)
    if mission.status != MissionStatus.EXECUTED:
        raise HTTPException(status_code=409, detail="Mission must be executed before verification")
    action_plan = plan_action(mission.decision.recommended_action, target=(mission.action or {}).get("target"))
    action_plan.payload["approved"] = True
    result = ACTION_EXECUTOR.execute(action_plan)
    verification = ACTION_VERIFIER.verify(result)
    mission.verification = {"status": verification.status, "checks": verification.checks, "details": verification.details, "verified_at": utc_now()}
    if verification.status != "verified":
        raise HTTPException(status_code=409, detail="Execution could not be verified")
    mission.status = MissionStatus.VERIFIED
    log_event(mission.audit, "verify", "تم التحقق من نتيجة التنفيذ وإغلاق دورة المهمة.")
    return _persist_mission(mission)
