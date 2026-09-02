from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from connectors.file_connector import FileConnector
from connectors.normalize import normalize_records
from core.models import BusinessContext, Evidence
from core.runtime import build_mission_orchestrator
from core.orchestrator import MissionState

app = FastAPI(
    title="NEXUS MVP",
    version="0.4.0",
    description="Goal-driven AI intelligence: Observe → Understand → Research → Reason → Decide → Act → Verify",
)


class MissionStatus(str, Enum):
    ANALYZING = "analyzing"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    EXECUTED = "executed"
    VERIFIED = "verified"
    BLOCKED = "blocked"
    VERIFICATION_FAILED = "verification_failed"


class SourceType(str, Enum):
    ERP = "erp"
    CONTRACT = "contract"
    SUPPLIER = "supplier"
    MARKET = "market"
    FILE = "file"
    CRM = "crm"
    ACTION = "action_executor"


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
    "operational": {"target_cost_reduction_pct": 10, "quality_floor": "unchanged", "active_contract_policy": "do_not_break"},
}

INGESTED_DATA: list[dict[str, Any]] = []
CORE_MISSIONS: dict[str, MissionState] = {}
ORCHESTRATOR = build_mission_orchestrator()


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


def _context_from_signals(signals: list[Signal]) -> BusinessContext:
    context = BusinessContext()
    for signal in signals:
        context.add_evidence(Evidence(id=signal.id, source=signal.source.value, claim=signal.title, value=signal.value, confidence=signal.confidence, metadata={"impact": signal.impact, "kind": "signal"}))
    return context


def reason(goal: str, constraints: list[str], signals: list[Signal]) -> Decision:
    """Compatibility helper: use the same evidence-aware decision engine as the API."""
    result = ORCHESTRATOR._reasoner(goal, constraints, _context_from_signals(signals))
    return Decision(**result)


def _signals_to_records(signals: list[Signal]) -> list[dict[str, Any]]:
    return [{"supplier": signal.title, "value": signal.value, "impact": signal.impact, "source": signal.source.value} for signal in signals]


def _status_for(core: MissionState) -> MissionStatus:
    return {
        "understand": MissionStatus.ANALYZING,
        "researching": MissionStatus.ANALYZING,
        "researched": MissionStatus.ANALYZING,
        "reason": MissionStatus.ANALYZING,
        "decide": MissionStatus.ANALYZING,
        "action_planned": MissionStatus.AWAITING_APPROVAL,
        "approved": MissionStatus.APPROVED,
        "executed": MissionStatus.EXECUTED,
        "verified": MissionStatus.VERIFIED,
        "execution_blocked": MissionStatus.BLOCKED,
        "verification_failed": MissionStatus.VERIFICATION_FAILED,
    }.get(core.stage, MissionStatus.ANALYZING)


def _audit(core: MissionState) -> list[AuditEvent]:
    return [AuditEvent(timestamp=item["timestamp"], stage=item["stage"], message=item["message"]) for item in core.audit]


def _to_api_mission(core: MissionState, signals: list[Signal], created_at: str) -> Mission:
    decision = Decision(**(core.decision or {}))
    completed = sum(1 for result in core.research_results if result.status == "completed")
    unavailable = sum(1 for result in core.research_results if result.status == "unavailable")
    evidence_added = sum(len(result.evidence) for result in core.research_results)
    action = None
    if core.action_plan:
        action = {
            "type": core.action_plan.action_type,
            "status": "approved" if core.stage == "approved" else (core.action_result.status if core.action_result else "planned"),
            "target": core.action_plan.payload.get("target"),
            "description": core.action_plan.description,
            "risk": core.action_plan.policy.risk.value,
            "approval_required": core.action_plan.policy.requires_approval,
        }
        if core.action_result:
            action["result"] = core.action_result.message
            action["output"] = core.action_result.output
    verification = None
    if core.verification:
        verification = {
            "status": core.verification.status,
            "checks": core.verification.checks,
            "details": core.verification.details,
        }
    return Mission(
        id=core.id,
        created_at=created_at,
        status=_status_for(core),
        goal=core.goal,
        constraints=core.constraints,
        sources_used=sorted({SourceType(s) for s in {e.source for e in core.context.evidence.values()} if s in {item.value for item in SourceType}}, key=lambda x: x.value),
        signals=signals,
        research=ResearchSummary(domains=core.goal_plan.domains() if core.goal_plan else [], completed=completed, unavailable=unavailable, evidence_added=evidence_added),
        decision=decision,
        action=action,
        verification=verification,
        audit=_audit(core),
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "nexus-mvp", "version": "0.4.0"}


@app.get("/api/context")
def context() -> dict[str, Any]:
    return {**SAMPLE_CONTEXT, "ingested_records": len(INGESTED_DATA)}


@app.post("/api/ingest/file")
def ingest_file(request: IngestRequest) -> dict[str, Any]:
    try:
        result = FileConnector().ingest(request.content, filename=request.filename)
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
    signals = sample_signals() + signals_from_ingestion()
    created_at = utc_now()
    core = ORCHESTRATOR.create(tenant_id="demo-tenant", goal=request.goal, constraints=request.constraints, records=_signals_to_records(signals), source="api-signals")
    ORCHESTRATOR.research(core)
    ORCHESTRATOR.decide(core)
    ORCHESTRATOR.plan(core, target="ABC Industrial")
    CORE_MISSIONS[core.id] = core
    return _to_api_mission(core, signals, created_at)


@app.get("/api/missions/{mission_id}", response_model=Mission)
def get_mission(mission_id: str) -> Mission:
    core = CORE_MISSIONS.get(mission_id)
    if not core:
        raise HTTPException(status_code=404, detail="Mission not found")
    signals = sample_signals() + signals_from_ingestion()
    created_at = next((item["timestamp"] for item in core.audit if item["stage"] == "observe"), utc_now())
    return _to_api_mission(core, signals, created_at)


@app.post("/api/missions/{mission_id}/approve", response_model=Mission)
def approve_mission(mission_id: str) -> Mission:
    core = CORE_MISSIONS.get(mission_id)
    if not core:
        raise HTTPException(status_code=404, detail="Mission not found")
    try:
        ORCHESTRATOR.approve(core)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    signals = sample_signals() + signals_from_ingestion()
    return _to_api_mission(core, signals, utc_now())


@app.post("/api/missions/{mission_id}/execute", response_model=Mission)
def execute_mission(mission_id: str) -> Mission:
    core = CORE_MISSIONS.get(mission_id)
    if not core:
        raise HTTPException(status_code=404, detail="Mission not found")
    try:
        ORCHESTRATOR.execute(core)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    signals = sample_signals() + signals_from_ingestion()
    return _to_api_mission(core, signals, utc_now())


@app.post("/api/missions/{mission_id}/verify", response_model=Mission)
def verify_mission(mission_id: str) -> Mission:
    core = CORE_MISSIONS.get(mission_id)
    if not core:
        raise HTTPException(status_code=404, detail="Mission not found")
    try:
        ORCHESTRATOR.verify(core)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    signals = sample_signals() + signals_from_ingestion()
    return _to_api_mission(core, signals, utc_now())
