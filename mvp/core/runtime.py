from __future__ import annotations

import os
from dataclasses import dataclass

from connectors.file_connector import FileConnector
from connectors.http_json_connector import HttpJsonConfig, HttpJsonConnector

from .action_executor import ActionExecutor, draft_email_handler
from .orchestrator import MissionOrchestrator
from .reasoner import reason_from_evidence
from .registry import ComponentRegistry
from .research_executor import ResearchExecutor, context_provider
from .verifier import ActionVerifier, draft_email_verifier


@dataclass(frozen=True, slots=True)
class MissionRuntime:
    """Single composition root for the mission lifecycle dependencies."""

    orchestrator: MissionOrchestrator
    action_executor: ActionExecutor
    verifier: ActionVerifier
    registry: ComponentRegistry


def _build_connector_registry() -> ComponentRegistry:
    registry = ComponentRegistry.empty()
    registry.add_connector("file", FileConnector())

    allowed_hosts = frozenset(
        host.strip()
        for host in os.getenv("NEXUS_HTTP_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    )
    if allowed_hosts:
        registry.add_connector(
            "http_json",
            HttpJsonConnector(
                HttpJsonConfig(
                    allowed_hosts=allowed_hosts,
                    timeout_seconds=float(os.getenv("NEXUS_HTTP_TIMEOUT_SECONDS", "10")),
                    max_response_bytes=int(os.getenv("NEXUS_HTTP_MAX_BYTES", "2000000")),
                )
            ),
        )
    return registry


def build_runtime() -> MissionRuntime:
    registry = _build_connector_registry()
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
    registry.add_executor("action", actions)
    registry.add_verifier("action", verifier)
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
        registry=registry,
    )


def build_mission_orchestrator() -> MissionOrchestrator:
    """Backward-compatible factory; new callers should prefer build_runtime()."""
    return build_runtime().orchestrator
