from __future__ import annotations

import httpx

from connectors.business_api_action import BusinessActionConnector
from connectors.business_api_connector import BusinessApiConnector
from connectors.file_connector import FileConnector
from connectors.http_json_connector import HttpJsonConnector
from core.action_executor import ActionExecutor
from core.ingestion_scheduler import SQLiteIngestionScheduler
from core.mission_repository import SQLiteMissionRepository
from core.orchestrator import MissionOrchestrator
from core.planner import plan_action
from core.runtime import MissionRuntime, build_mission_orchestrator, build_runtime
from core.verifier import ActionVerifier


def test_runtime_composes_one_shared_dependency_graph():
    runtime = build_runtime()
    assert isinstance(runtime, MissionRuntime)
    assert isinstance(runtime.orchestrator, MissionOrchestrator)
    assert isinstance(runtime.action_executor, ActionExecutor)
    assert isinstance(runtime.verifier, ActionVerifier)
    assert runtime.orchestrator.action_executor is runtime.action_executor
    assert runtime.orchestrator.verifier is runtime.verifier
    assert isinstance(runtime.registry.connectors["file"], FileConnector)
    assert runtime.registry.executors["action"] is runtime.action_executor
    assert runtime.registry.verifiers["action"] is runtime.verifier
    assert isinstance(runtime.mission_repository, SQLiteMissionRepository)
    assert isinstance(runtime.ingestion_scheduler, SQLiteIngestionScheduler)
    assert "http_json" not in runtime.registry.connectors


def test_runtime_registers_http_json_when_hosts_are_configured(monkeypatch):
    monkeypatch.setenv("NEXUS_HTTP_ALLOWED_HOSTS", "api.example.test, reports.example.test ")
    runtime = build_runtime()

    assert isinstance(runtime.registry.connectors["http_json"], HttpJsonConnector)
    assert runtime.registry.describe()["connectors"] == ["file", "http_json"]


def test_runtime_registers_configured_business_connectors(monkeypatch):
    monkeypatch.setenv("NEXUS_HTTP_ALLOWED_HOSTS", "erp.example.test,crm.example.test,supplier.example.test")
    monkeypatch.setenv("NEXUS_ERP_URL", "https://erp.example.test")
    monkeypatch.setenv("NEXUS_ERP_ENDPOINT", "/api/orders")
    monkeypatch.setenv("NEXUS_ERP_TOKEN_ENV", "ERP_TOKEN")
    monkeypatch.setenv("NEXUS_CRM_URL", "https://crm.example.test")
    monkeypatch.setenv("NEXUS_CRM_ENDPOINT", "/api/opportunities")
    monkeypatch.setenv("NEXUS_SUPPLIER_URL", "https://supplier.example.test")
    monkeypatch.setenv("NEXUS_SUPPLIER_ENDPOINT", "/api/suppliers")

    runtime = build_runtime()

    assert isinstance(runtime.registry.connectors["erp"], BusinessApiConnector)
    assert isinstance(runtime.registry.connectors["crm"], BusinessApiConnector)
    assert isinstance(runtime.registry.connectors["supplier"], BusinessApiConnector)
    assert {"erp", "crm", "supplier"}.issubset(runtime.registry.describe()["connectors"])


def test_business_connectors_remain_disabled_without_explicit_urls(monkeypatch):
    for name in ("ERP", "CRM", "SUPPLIER"):
        monkeypatch.delenv(f"NEXUS_{name}_URL", raising=False)
        monkeypatch.delenv(f"NEXUS_{name}_ENDPOINT", raising=False)
    runtime = build_runtime()

    assert "erp" not in runtime.registry.connectors
    assert "crm" not in runtime.registry.connectors
    assert "supplier" not in runtime.registry.connectors


def test_runtime_registers_and_executes_real_action(monkeypatch):
    monkeypatch.setenv("NEXUS_HTTP_ALLOWED_HOSTS", "crm.example.test")
    monkeypatch.setenv("NEXUS_ACTION_URL", "https://crm.example.test")
    monkeypatch.setenv("NEXUS_ACTION_ENDPOINT", "/api/opportunities/42")
    monkeypatch.setenv("NEXUS_ACTION_METHOD", "PATCH")

    captured = {}

    class MockClient:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def request(self, method, url, **kwargs):
            captured.update(method=method, url=url, **kwargs)
            return httpx.Response(200, json={"updated": True}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "Client", MockClient)
    runtime = build_runtime()

    assert isinstance(runtime.registry.connectors["business_action"], BusinessActionConnector)
    plan = plan_action("Update CRM", target="opportunity-42", action_type="update_crm", body={"stage": "negotiation"})
    approved = type(plan)(plan.action_type, plan.description, plan.policy, {**plan.payload, "approved": True})
    result = runtime.action_executor.execute(approved)

    assert result.status == "completed"
    assert result.execution_id
    assert captured["headers"]["Idempotency-Key"] == result.execution_id
    assert captured["json"] if "json" in captured else captured["content"]


def test_legacy_factory_still_returns_orchestrator():
    assert isinstance(build_mission_orchestrator(), MissionOrchestrator)


def test_runtime_exports_are_stable_from_core_package():
    from core import GoalProfile, MissionRuntime, build_runtime, classify_goal

    profile = classify_goal("Increase sales revenue")
    runtime = build_runtime()
    assert profile.key == "revenue"
    assert isinstance(profile, GoalProfile)
    assert isinstance(runtime, MissionRuntime)


def test_orchestrator_lifecycle_dependencies_are_public_and_idempotent():
    orchestrator = build_mission_orchestrator()
    assert orchestrator.action_executor is not None
    assert orchestrator.verifier is not None

    mission = orchestrator.create(tenant_id="demo", goal="خفض تكلفة التشغيل 10%")
    orchestrator.decide(mission)
    orchestrator.plan(mission, target="ABC")
    orchestrator.approve(mission)
    orchestrator.execute(mission)
    first_execution = mission.action_result
    orchestrator.execute(mission)
    assert mission.action_result is first_execution

    orchestrator.verify(mission)
    first_verification = mission.verification
    orchestrator.verify(mission)
    assert mission.verification is first_verification
