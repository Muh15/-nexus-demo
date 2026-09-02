from connectors.http_json_connector import HttpJsonConfig, HttpJsonConnector
from core.models import BusinessContext
from core.research_executor import http_json_provider
from core.research_planner import ResearchTask


def test_http_json_provider_turns_records_into_provenance_backed_evidence(monkeypatch):
    connector = HttpJsonConnector(
        HttpJsonConfig(allowed_hosts=frozenset({"api.example.test"}))
    )

    def fake_fetch(url, *, headers=None):
        assert url == "https://api.example.test/feed"
        assert headers == {"Authorization": "Bearer test"}
        from connectors.base import ConnectorResult

        return ConnectorResult(
            source="http_json",
            records=[{"supplier": "ABC", "price_change_pct": 7}],
            metadata={"sha256": "abc123", "status_code": 200},
            provenance=[{"locator": "item:1"}],
        )

    monkeypatch.setattr(connector, "fetch", fake_fetch)
    provider = http_json_provider(
        connector,
        "https://api.example.test/feed",
        headers={"Authorization": "Bearer test"},
    )
    task = ResearchTask(
        domain="regulatory",
        question="هل توجد تغيّرات تنظيمية؟",
        reason="اختبار مصدر خارجي",
        priority=90,
        connector="web",
    )

    result = provider(task, BusinessContext())

    assert result.status == "completed"
    assert len(result.evidence) == 1
    evidence = result.evidence[0]
    assert evidence.source == "http_json"
    assert evidence.value["supplier"] == "ABC"
    assert evidence.locator == "item:1"
    assert evidence.metadata["sha256"] == "abc123"
    assert evidence.metadata["url"] == "https://api.example.test/feed"


def test_http_json_provider_converts_transport_errors_to_unavailable(monkeypatch):
    connector = HttpJsonConnector(
        HttpJsonConfig(allowed_hosts=frozenset({"api.example.test"}))
    )

    def fake_fetch(url, *, headers=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(connector, "fetch", fake_fetch)
    provider = http_json_provider(connector, "https://api.example.test/feed")
    task = ResearchTask(
        domain="regulatory",
        question="هل توجد تغيّرات تنظيمية؟",
        reason="اختبار فشل المصدر",
        priority=90,
        connector="web",
    )

    result = provider(task, BusinessContext())

    assert result.status == "unavailable"
    assert "boom" in result.message
