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
