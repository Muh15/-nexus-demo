import hashlib
import json

import pytest

from connectors.business_api_connector import BusinessApiConfig, BusinessApiConnector


class _Response:
    status_code = 200
    content = b'{"items":[{"id":1},{"id":2}],"next_cursor":"abc"}'
    headers = {"content-type": "application/json"}

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return json.loads(self.content)


class _Client:
    last_kwargs = None

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        _Client.last_kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, params=None):
        assert url == "https://erp.example.test/api/orders"
        assert params == {"cursor": "old"}
        return _Response()


def test_business_connector_fetches_scoped_records_and_cursor(monkeypatch):
    monkeypatch.setattr("connectors.business_api_connector.httpx.Client", _Client)
    monkeypatch.setenv("ERP_API_TOKEN", "secret-value")
    connector = BusinessApiConnector(
        BusinessApiConfig(
            name="erp",
            base_url="https://erp.example.test",
            allowed_hosts=frozenset({"erp.example.test"}),
            token_env="ERP_API_TOKEN",
        )
    )

    result = connector.fetch("/api/orders", cursor="old")

    assert result.records == [{"id": 1}, {"id": 2}]
    assert result.metadata["next_cursor"] == "abc"
    assert result.metadata["sha256"] == hashlib.sha256(_Response.content).hexdigest()
    assert _Client.last_kwargs["headers"]["Authorization"] == "Bearer secret-value"
    assert result.metadata["credential_env"] == "ERP_API_TOKEN"


def test_business_connector_rejects_base_url_outside_allow_list():
    with pytest.raises(ValueError, match="allow-listed"):
        BusinessApiConnector(
            BusinessApiConfig(
                name="crm",
                base_url="https://crm.example.test",
                allowed_hosts=frozenset({"erp.example.test"}),
            )
        )


def test_business_connector_does_not_require_token(monkeypatch):
    monkeypatch.delenv("CRM_API_TOKEN", raising=False)
    connector = BusinessApiConnector(
        BusinessApiConfig(
            name="crm",
            base_url="https://crm.example.test",
            allowed_hosts=frozenset({"crm.example.test"}),
            token_env="CRM_API_TOKEN",
        )
    )
    assert connector.name == "crm"


def test_business_connector_accepts_wrapped_data_objects():
    class Wrapped:
        def json(self):
            return {"data": [{"id": "x"}]}

    assert BusinessApiConnector._records_and_cursor(Wrapped().json()) == ([{"id": "x"}], None)
