from main import reason, sample_signals
from connectors.file_connector import FileConnector
from connectors.normalize import normalize_records


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


def test_file_connector_csv_and_normalization():
    csv_text = "Supplier,Monthly Spend,Price Change,Contract Days Left\nAcme,500000,8%,45\n"
    result = FileConnector().ingest(csv_text, filename="suppliers.csv")
    records = normalize_records(result.records)
    assert result.metadata["record_count"] == 1
    assert records[0]["supplier"] == "Acme"
    assert records[0]["monthly_spend"] == 500000
    assert records[0]["price_change_pct"] == 8
    assert records[0]["contract_days_left"] == 45


def test_file_connector_rejects_unknown_format():
    try:
        FileConnector().ingest("hello", filename="data.xlsx")
    except ValueError as exc:
        assert "Unsupported file type" in str(exc)
    else:
        raise AssertionError("Expected unsupported file type error")
