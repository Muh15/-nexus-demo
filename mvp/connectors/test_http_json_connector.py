from __future__ import annotations

import hashlib
import json

import pytest

from connectors.http_json_connector import HttpJsonConfig, HttpJsonConnector


class _FakeResponse:
    status_code = 200
    content = b'{"supplier":"alpha","price":120}'
    headers = {"content-type": "application/json"}

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return json.loads(self.content)


class _FakeClient:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str):
        assert url == "https://api.example.test/data"
        return _FakeResponse()


def test_http_json_connector_fetches_allow_listed_json(monkeypatch) -> None:
    monkeypatch.setattr("connectors.http_json_connector.httpx.Client", _FakeClient)
    connector = HttpJsonConnector(HttpJsonConfig(frozenset({"api.example.test"})))

    result = connector.fetch("https://api.example.test/data")

    assert result.source == "http_json"
    assert result.records == [{"supplier": "alpha", "price": 120}]
    assert result.metadata["record_count"] == 1
    assert result.metadata["sha256"] == hashlib.sha256(_FakeResponse.content).hexdigest()
    assert result.provenance[0]["url"] == "https://api.example.test/data"


def test_http_json_connector_rejects_non_allow_listed_host() -> None:
    connector = HttpJsonConnector(HttpJsonConfig(frozenset({"api.example.test"})))

    with pytest.raises(ValueError, match="allow-listed"):
        connector.fetch("https://evil.example.test/data")


def test_http_json_connector_rejects_unsupported_scheme() -> None:
    connector = HttpJsonConnector(HttpJsonConfig(frozenset({"api.example.test"})))

    with pytest.raises(ValueError, match="http and https"):
        connector.fetch("file:///tmp/data.json")


def test_http_json_connector_accepts_array_of_objects(monkeypatch) -> None:
    class ArrayResponse(_FakeResponse):
        content = b'[{"id":1},{"id":2}]'

        def json(self):
            return json.loads(self.content)

    class ArrayClient(_FakeClient):
        def get(self, url: str):
            return ArrayResponse()

    monkeypatch.setattr("connectors.http_json_connector.httpx.Client", ArrayClient)
    connector = HttpJsonConnector(HttpJsonConfig(frozenset({"api.example.test"})))

    result = connector.ingest("https://api.example.test/data")

    assert result.records == [{"id": 1}, {"id": 2}]
    assert result.metadata["record_count"] == 2
