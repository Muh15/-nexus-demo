from core.action_executor import ActionExecutor
from core.orchestrator import MissionOrchestrator
from core.runtime import MissionRuntime, build_mission_orchestrator, build_runtime
from core.verifier import ActionVerifier


def test_runtime_composes_one_shared_dependency_graph():
    runtime = build_runtime()
    assert isinstance(runtime, MissionRuntime)
    assert isinstance(runtime.orchestrator, MissionOrchestrator)
    assert isinstance(runtime.action_executor, ActionExecutor)
    assert isinstance(runtime.verifier, ActionVerifier)
    assert runtime.orchestrator._action_executor is runtime.action_executor
    assert runtime.orchestrator._verifier is runtime.verifier


def test_legacy_factory_still_returns_orchestrator():
    assert isinstance(build_mission_orchestrator(), MissionOrchestrator)


def test_runtime_exports_are_stable_from_core_package():
    from core import GoalProfile, MissionRuntime, build_runtime, classify_goal

    profile = classify_goal("Increase sales revenue")
    runtime = build_runtime()
    assert profile.key == "revenue"
    assert isinstance(profile, GoalProfile)
    assert isinstance(runtime, MissionRuntime)
