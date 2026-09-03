from connectors.base import ConnectorResult
from connectors.business_api_pagination import fetch_all_pages


def test_fetch_all_pages_follows_cursor_until_complete():
    pages = {
        None: ConnectorResult("crm", [{"id": 1}], {"next_cursor": "c1"}),
        "c1": ConnectorResult("crm", [{"id": 2}], {"next_cursor": "c2"}),
        "c2": ConnectorResult("crm", [{"id": 3}], {}),
    }
    result = fetch_all_pages(lambda cursor: pages[cursor], max_pages=5)
    assert result.records == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert result.cursor is None
    assert result.pages == 3


def test_fetch_all_pages_rejects_repeated_cursor():
    def fetch(cursor):
        return ConnectorResult("crm", [{"id": cursor}], {"next_cursor": "same"})

    try:
        fetch_all_pages(fetch, max_pages=5)
    except ValueError as exc:
        assert "cursor repeated" in str(exc)
    else:
        raise AssertionError("expected repeated cursor failure")


def test_fetch_all_pages_stops_at_bound():
    result = fetch_all_pages(lambda _: ConnectorResult("crm", [{"id": 1}], {"next_cursor": "next"}), max_pages=2)
    assert result.pages == 2
    assert result.cursor == "next"
