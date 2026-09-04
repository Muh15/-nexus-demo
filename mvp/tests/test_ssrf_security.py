from __future__ import annotations

import socket

import pytest

from connectors.business_api_action import BusinessActionConfig, BusinessActionConnector
from connectors.http_json_connector import HttpJsonConfig, HttpJsonConnector


def test_http_connector_rejects_private_dns_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    )
    connector = HttpJsonConnector(HttpJsonConfig(allowed_hosts=frozenset({"internal.example"})))
    with pytest.raises(ValueError, match="non-public"):
        connector._validate_url("https://internal.example/data")


def test_action_connector_rejects_private_dns_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443))],
    )
    with pytest.raises(ValueError, match="non-public"):
        BusinessActionConnector(
            BusinessActionConfig(
                name="crm",
                base_url="https://crm.example/api",
                allowed_hosts=frozenset({"crm.example"}),
            )
        )


def test_http_connector_rejects_private_ip_literal() -> None:
    connector = HttpJsonConnector(HttpJsonConfig(allowed_hosts=frozenset({"127.0.0.1"})))
    with pytest.raises(ValueError, match="non-public"):
        connector._validate_url("http://127.0.0.1/data")


def test_action_connector_rejects_url_credentials() -> None:
    with pytest.raises(ValueError, match="credentials"):
        BusinessActionConnector(
            BusinessActionConfig(
                name="crm",
                base_url="https://user:pass@crm.example/api",
                allowed_hosts=frozenset({"crm.example"}),
            )
        )
