from __future__ import annotations

import os
from dataclasses import dataclass

from connectors.business_api_connector import BusinessApiConfig, BusinessApiConnector
from connectors.file_connector import FileConnector
from connectors.http_json_connector import HttpJsonConfig, HttpJsonConnector

from .action_executor import ActionExecutor, draft_email_handler
from .ingestion_scheduler import SQLiteIngestionScheduler
from .mission_repository import SQLiteMissionRepository
from .orchestrator import MissionOrchestrator
from .reasoner import reason_from_evidence
from .registry import ComponentRegistry
from .research_executor import ResearchExecutor, business_api_provider, context_provider, http_json_provider
from .sqlite_store import SQLiteMissionStore
from .verifier import ActionVerifier, draft_email_verifier


@dataclass(frozen=True, slots=True)
class MissionRuntime:
    """Single composition root for the mission lifecycle dependencies."""

    orchestrator: MissionOrchestrator
    action_executor: ActionExecutor
    verifier: ActionVerifier
    registry: ComponentRegistry
    mission_repository: SQLiteMissionRepository
    ingestion_scheduler: SQLiteIngestionScheduler


def _build_connector_registry() -> ComponentRegistry:
    registry = ComponentRegistry.empty()
    registry.add_connector("file", FileConnector())
    allowed_hosts = frozenset(host.strip() for host in os.getenv("NEXUS_HTTP_ALLOWED_HOSTS", "").split(",") if host.strip())
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

    # Business systems are opt-in. Each connector is enabled only when its
    # base URL is explicitly configured and the hostname is present in the
    # same allow-list used for outbound HTTP policy.
    business_specs = {
        "erp": ("NEXUS_ERP_URL", "NEXUS_ERP_TOKEN_ENV", "NEXUS_ERP_ENDPOINT"),
        "crm": ("NEXUS_CRM_URL", "NEXUS_CRM_TOKEN_ENV", "NEXUS_CRM_ENDPOINT"),
        "supplier": ("NEXUS_SUPPLIER_URL", "NEXUS_SUPPLIER_TOKEN_ENV", "NEXUS_SUPPLIER_ENDPOINT"),
    }
    for name, (url_env, token_env_env, _) in business_specs.items():
        base_url = os.getenv(url_env, "").strip()
        if not base_url:
            continue
        token_env = os.getenv(token_env_env, "").strip() or None
        registry.add_connector(
            name,
            BusinessApiConnector(
                BusinessApiConfig(
                    name=name,
                    base_url=base_url,
                    allowed_hosts=allowed_hosts,
                    token_env=token_env,
                    timeout_seconds=float(os.getenv("NEXUS_BUSINESS_TIMEOUT_SECONDS", "10")),
                    max_response_bytes=int(os.getenv("NEXUS_BUSINESS_MAX_BYTES", "2000000")),
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

    # Replace the deterministic provider with a real, scoped business API when
    # the relevant URL + endpoint are configured. Planner contracts stay stable.
    for name in ("erp", "crm", "supplier"):
        connector = registry.connectors.get(name)
        endpoint_env = f"NEXUS_{name.upper()}_ENDPOINT"
        endpoint = os.getenv(endpoint_env, "").strip()
        if isinstance(connector, BusinessApiConnector) and endpoint:
            research._providers[name] = business_api_provider(connector, endpoint, confidence=90)

    # When an allow-listed HTTP JSON endpoint is explicitly configured, use it
    # as the real transport for web research. Without the URL, the deterministic
    # local provider remains active so tests and demos stay offline and stable.
    http_research_url = os.getenv("NEXUS_HTTP_RESEARCH_URL", "").strip()
    http_connector = registry.connectors.get("http_json")
    if http_research_url and isinstance(http_connector, HttpJsonConnector):
        research.register(
            "http_json",
            http_json_provider(http_connector, http_research_url, confidence=88),
        )
        research.register(
            "web_http",
            http_json_provider(http_connector, http_research_url, confidence=88),
        )
        research._providers["web"] = http_json_provider(http_connector, http_research_url, confidence=88)

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
    repository_path = os.getenv("NEXUS_DB_PATH", "nexus_mvp.sqlite3")
    repository = SQLiteMissionRepository(SQLiteMissionStore(repository_path))
    scheduler = SQLiteIngestionScheduler(repository_path)
    return MissionRuntime(
        orchestrator=orchestrator,
        action_executor=actions,
        verifier=verifier,
        registry=registry,
        mission_repository=repository,
        ingestion_scheduler=scheduler,
    )


def build_mission_orchestrator() -> MissionOrchestrator:
    """Backward-compatible factory; new callers should prefer build_runtime()."""
    return build_runtime().orchestrator
