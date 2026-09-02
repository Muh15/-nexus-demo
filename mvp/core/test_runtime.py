from connectors.file_connector import FileConnector
from connectors.http_json_connector import HttpJsonConnector
from core.action_executor import ActionExecutor
from core.mission_repository import SQLiteMissionRepository
from core.orchestrator import MissionOrchestrator
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
    assert "http_json" not in runtime.registry.connectors


def test_runtime_registers_http_json_when_hosts_are_configured(monkeypatch):
    monkeypatch.setenv("NEXUS_HTTP_ALLOWED_HOSTS", "api.example.test, reports.example.test ")
    runtime = build_runtime()

    assert isinstance(runtime.registry.connectors["http_json"], HttpJsonConnector)
    assert runtime.registry.describe()["connectors"] == ["file", "http_json"]


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
