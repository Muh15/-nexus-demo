from __future__ import annotations

from dataclasses import dataclass

from .action_executor import ActionExecutor, draft_email_handler
from .orchestrator import MissionOrchestrator
from .reasoner import reason_from_evidence
from .research_executor import ResearchExecutor, context_provider
from .verifier import ActionVerifier, draft_email_verifier


@dataclass(frozen=True, slots=True)
class MissionRuntime:
    """Single composition root for the mission lifecycle dependencies."""

    orchestrator: MissionOrchestrator
    action_executor: ActionExecutor
    verifier: ActionVerifier


def build_runtime() -> MissionRuntime:
    research = ResearchExecutor()
    for connector, source in {
        "file": "file",
        "supplier": "supplier_connector",
        "erp": "erp_connector",
        "contract": "contract_connector",
        "market": "market_connector",
        "crm": "crm_connector",
        "web": "web_connector",
    }.items():
        research.register(connector, context_provider(connector, source, confidence=82))

    actions = ActionExecutor({"draft_email": draft_email_handler})
    verifier = ActionVerifier({"draft_email": draft_email_verifier})
    orchestrator = MissionOrchestrator(
        lambda goal, constraints, context: reason_from_evidence(goal, constraints, context).as_dict(),
        research_executor=research,
        action_executor=actions,
        verifier=verifier,
    )
    return MissionRuntime(
        orchestrator=orchestrator,
        action_executor=actions,
        verifier=verifier,
    )


def build_mission_orchestrator() -> MissionOrchestrator:
    """Backward-compatible factory; new callers should prefer build_runtime()."""
    return build_runtime().orchestrator
