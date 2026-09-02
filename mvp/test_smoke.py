from io import BytesIO

from connectors.file_connector import FileConnector
from core.change_detector import detect_change, detect_record_changes
from core.context_builder import build_context
from core.goal_planner import build_goal_plan, parse_goal
from core.impact import assess_change
from core.intelligence_graph import IntelligenceGraph
from core.memory import MemoryStore
from core.mission_intelligence import MissionIntelligence
from core.models import BusinessContext, Entity, Evidence, Relationship
from core.orchestrator import MissionOrchestrator
from core.planner import plan_action
from core.policy import ActionRisk, evaluate_action
from core.research_executor import ResearchExecutor, context_provider
from core.research_planner import build_research_plan
from main import reason, sample_signals


def test_cost_reduction_reasoning():
    decision = reason(
        "Reduce operating cost by 10% within 90 days",
        ["Do not change quality", "Do not break active contracts"],
        sample_signals(),
    )
    assert decision.confidence >= 90
    assert "تفاوض" in decision.recommended_action
    assert len(decision.rationale) >= 3


def test_signals_cover_multiple_sources():
    sources = {signal.source.value for signal in sample_signals()}
    assert {"erp", "contract", "supplier", "market"}.issubset(sources)


def test_csv_connector_preserves_provenance():
    result = FileConnector().ingest(
        "supplier,monthly_spend\nABC,420000\n",
        filename="spend.csv",
    )
    assert result.metadata["format"] == "csv"
    assert result.records[0]["supplier"] == "ABC"
    assert result.provenance[0]["locator"] == "row:2"
    assert len(result.metadata["sha256"]) == 64


def test_xlsx_connector_reads_sheet_rows():
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Spend"
    sheet.append(["supplier", "monthly_spend"])
    sheet.append(["ABC", 420000])
    stream = BytesIO()
    workbook.save(stream)

    result = FileConnector().ingest(stream.getvalue(), filename="spend.xlsx")
    assert result.records[0]["supplier"] == "ABC"
    assert result.provenance[0]["locator"] == "sheet:Spend!row:2"


def test_business_context_keeps_relationship_evidence():
    context = BusinessContext()
    context.add_entity(Entity("supplier:abc", "supplier", "ABC Industrial"))
    context.add_entity(Entity("contract:abc", "contract", "ABC-2026"))
    context.add_evidence(Evidence("ev-1", "contract", "renewal_window", 43, confidence=94))
    context.link(Relationship("supplier:abc", "governed_by", "contract:abc", 98, ["ev-1"]))
    snapshot = context.snapshot()
    assert snapshot["relationships"][0]["evidence_ids"] == ["ev-1"]


def test_context_builder_links_supplier_to_contract():
    context = build_context(
        [{"supplier": "ABC", "contract": "ABC-2026", "monthly_spend": 420000}],
        source="xlsx",
    )
    assert "supplier:abc" in context.entities
    assert "contract:abc-2026" in context.entities
    assert context.relationships[0].relation == "governed_by"
    assert context.entities["supplier:abc"].attributes["amounts"] == [420000]


def test_action_policy_is_default_deny_for_critical_actions():
    policy = evaluate_action("transfer_money", amount=1000)
    assert policy.risk is ActionRisk.CRITICAL
    assert policy.allowed is False
    assert policy.requires_approval is True


def test_planner_keeps_action_separate_from_decision():
    plan = plan_action("ابدأ التفاوض مع المورد", target="ABC Industrial")
    assert plan.action_type == "draft_email"
    assert plan.policy.allowed is True
    assert plan.payload["approval_required"] is True


def test_memory_is_temporal_and_tenant_isolated():
    memory = MemoryStore()
    first = memory.remember("tenant-a", "supplier:abc:price", 100, source="erp")
    second = memory.remember("tenant-a", "supplier:abc:price", 108, source="erp")
    memory.remember("tenant-b", "supplier:abc:price", 999, source="erp")

    assert memory.latest("tenant-a", "supplier:abc:price") is second
    assert [item.value for item in memory.history("tenant-a", "supplier:abc:price")] == [100, 108]
    assert memory.snapshot("tenant-b")["facts"]["supplier:abc:price"]["value"] == 999
    assert first.tenant_id == "tenant-a"


def test_change_detector_identifies_new_updated_and_unchanged():
    memory = MemoryStore()
    created = detect_change(memory, "tenant-a", "contract:abc:price", 100, source="erp")
    same = detect_change(memory, "tenant-a", "contract:abc:price", 100, source="erp")
    updated = detect_change(memory, "tenant-a", "contract:abc:price", 112, source="erp")

    assert created.kind == "new"
    assert same.kind == "unchanged"
    assert updated.kind == "updated"
    assert updated.previous == 100
    assert updated.current == 112


def test_record_change_detection_uses_deterministic_identity():
    memory = MemoryStore()
    rows = [{"supplier": "ABC", "monthly_spend": 420000, "status": "active"}]
    first = detect_record_changes(memory, "tenant-a", rows, source="xlsx")
    second = detect_record_changes(memory, "tenant-a", rows, source="xlsx")

    assert any(item.kind == "new" for item in first)
    assert all(item.kind == "unchanged" for item in second)


def test_goal_planner_is_domain_agnostic_and_prioritizes_research_needs():
    goal = parse_goal(
        "Reduce operating cost by 10% within 90 days",
        ["Do not change quality", "Do not break active contracts"],
    )
    plan = build_goal_plan(goal)

    assert goal.target_value == 10
    assert goal.target_unit == "%"
    assert goal.horizon == "90 days"
    assert "operations" in plan.domains()
    assert "suppliers" in plan.domains()
    assert "contracts" in plan.domains()


def test_goal_planner_has_safe_fallback_for_ambiguous_goal():
    goal = parse_goal("تحسين تجربة العملاء")
    plan = build_goal_plan(goal)
    assert plan.domains() == ["business_context"]


def test_intelligence_graph_projects_context_without_owning_source_data():
    context = BusinessContext()
    context.add_entity(Entity("supplier:abc", "supplier", "ABC Industrial"))
    context.add_entity(Entity("contract:abc", "contract", "ABC-2026"))
    context.add_evidence(Evidence("ev-1", "contract", "renewal_window", 43, confidence=94))
    context.link(Relationship("supplier:abc", "governed_by", "contract:abc", 98, ["ev-1"]))

    graph = IntelligenceGraph.from_context(context)
    neighbors = graph.neighbors("supplier:abc", relation="governed_by")
    evidence = graph.supporting_evidence("supplier:abc", context.evidence.values())

    assert neighbors[0].id == "contract:abc"
    assert evidence[0].id == "ev-1"
    assert graph.snapshot()["edges"][0]["evidence_ids"] == ["ev-1"]


def test_impact_assessment_prioritizes_goal_relevant_updates():
    memory = MemoryStore()
    change = detect_change(memory, "tenant-a", "supplier:abc:monthly_spend", 420000, source="erp")
    goal = parse_goal("Reduce operating cost by 10% within 90 days")
    plan = build_goal_plan(goal)
    assessment = assess_change(change, goal, plan.research_needs)

    assert assessment.relevant is True
    assert assessment.score >= 55


def test_mission_intelligence_combines_memory_and_goal_plan():
    intelligence = MissionIntelligence()
    rows = [{"supplier": "ABC", "monthly_spend": 420000, "status": "active"}]
    first_plan, first_changes, first_assessments = intelligence.prepare(
        tenant_id="tenant-a",
        goal_text="Reduce operating cost by 10% within 90 days",
        records=rows,
        source="xlsx",
    )
    second_plan, second_changes, second_assessments = intelligence.prepare(
        tenant_id="tenant-a",
        goal_text="Reduce operating cost by 10% within 90 days",
        records=rows,
        source="xlsx",
    )

    assert "suppliers" in first_plan.domains()
    assert any(item.kind == "new" for item in first_changes)
    assert all(item.kind == "unchanged" for item in second_changes)
    assert second_plan.goal.objective == first_plan.goal.objective
    assert len(first_assessments) == len(second_assessments)


def test_adaptive_research_planner_finds_missing_domains():
    goal_plan = build_goal_plan(parse_goal("Reduce operating cost by 10% within 90 days"))
    context = build_context([{"supplier": "ABC", "monthly_spend": 420000}], source="erp")
    research = build_research_plan(goal_plan, context)

    assert research.tasks
    assert any(task.domain == "contracts" for task in research.tasks)
    assert all(task.connector for task in research.tasks)
    assert research.tasks == sorted(research.tasks, key=lambda item: (-item.priority, item.domain))


def test_research_executor_collects_evidence_through_replaceable_provider():
    context = build_context([{"supplier": "ABC", "monthly_spend": 420000}], source="erp")
    goal_plan = build_goal_plan(parse_goal("Reduce operating cost by 10% within 90 days"))
    plan = build_research_plan(goal_plan, context)
    executor = ResearchExecutor()
    executor.register("contract", context_provider("contract", "contract_api"))

    plan.tasks = [task for task in plan.tasks if task.domain == "contracts"]
    results = executor.execute(plan, context)

    assert len(results) == 1
    assert results[0].status == "completed"
    assert results[0].evidence
    assert results[0].evidence[0].source == "contract_api"


def test_orchestrator_research_stage_is_explicit_and_replaceable():
    def fake_reasoner(goal, constraints, context):
        return {
            "title": "قرار تجريبي",
            "recommended_action": "إعداد مسودة متابعة",
            "confidence": 90,
        }

    executor = ResearchExecutor({"contract": context_provider("contract", "contract_api")})
    orchestrator = MissionOrchestrator(fake_reasoner, research_executor=executor)
    mission = orchestrator.create(
        tenant_id="tenant-a",
        goal="Reduce operating cost by 10% within 90 days",
        constraints=["Do not change quality"],
        records=[{"supplier": "ABC", "monthly_spend": 420000}],
        source="xlsx",
    )
    orchestrator.research(mission)

    assert mission.stage == "researched"
    assert mission.research_plan is not None
    assert mission.research_results

    orchestrator.decide(mission)
    orchestrator.plan(mission, target="ABC Industrial")
    assert mission.stage == "action_planned"
    assert mission.goal_plan is not None
    assert mission.intelligence_graph is not None
    assert mission.impact_assessments
    assert mission.action_plan is not None
