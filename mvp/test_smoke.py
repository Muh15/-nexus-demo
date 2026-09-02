from io import BytesIO

from connectors.file_connector import FileConnector
from core.models import BusinessContext, Entity, Evidence, Relationship
from core.policy import ActionRisk, evaluate_action
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


def test_action_policy_is_default_deny_for_critical_actions():
    policy = evaluate_action("transfer_money", amount=1000)
    assert policy.risk is ActionRisk.CRITICAL
    assert policy.allowed is False
    assert policy.requires_approval is True
