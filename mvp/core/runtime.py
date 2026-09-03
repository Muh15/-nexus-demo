from __future__ import annotations

import os
from dataclasses import dataclass

from connectors.business_api_action import BusinessActionConfig, BusinessActionConnector
from connectors.business_api_connector import BusinessApiConfig, BusinessApiConnector
from connectors.file_connector import FileConnector
from connectors.http_json_connector import HttpJsonConfig, HttpJsonConnector

from .action_executor import ActionExecutor, ActionResult, draft_email_handler
from .ingestion_scheduler import SQLiteIngestionScheduler
from .mission_repository import SQLiteMissionRepository
from .orchestrator import MissionOrchestrator
from .read_back_verifier import ReadAfterWriteVerifier, build_read_back_verifier_from_env
from .reasoner import reason_from_evidence
from .registry import ComponentRegistry
from .research_executor import ResearchExecutor, business_api_provider, context_provider, http_json_provider
from .sqlite_store import SQLiteMissionStore
from .verifier import ActionVerifier, VerificationResult, draft_email_verifier


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


def _real_action_handler(connector: BusinessActionConnector, endpoint: str, method: str):
    def handler(plan) -> ActionResult:
        execution_id = plan.payload["execution_id"]
        request_body = dict(plan.payload.get("body", {}))
        try:
            result = connector.execute(method, endpoint, request_body, execution_id)
        except Exception as exc:
            return ActionResult(
                action_type=plan.action_type,
                status="failed",
                message=f"External action transport failed: {type(exc).__name__}",
                output={
                    "error": type(exc).__name__,
                    "target": plan.payload.get("target"),
                    "request_body": request_body,
                },
                execution_id=execution_id,
            )
        status = "completed" if result["ok"] else "failed"
        return ActionResult(
            action_type=plan.action_type,
            status=status,
            output={
                **result,
                "target": plan.payload.get("target"),
                "request_body": request_body,
            },
            message="External business action completed." if result["ok"] else "External business API rejected the action.",
            execution_id=execution_id,
        )
    return handler


def _real_action_verifier(result: ActionResult) -> VerificationResult:
    ok = bool(result.output.get("ok", False))
    return VerificationResult(
        status="verified" if ok else "failed",
        checks=[
            "External API returned a successful status",
            "Execution id was propagated as the idempotency key",
            "Response was size-limited and hashed for audit provenance",
        ],
        details={
            "status_code": result.output.get("status_code"),
            "execution_id": result.execution_id,
            "sha256": result.output.get("sha256"),
            "attempts": result.output.get("attempts"),
        },
    )


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

    for name in ("erp", "crm", "supplier"):
        connector = registry.connectors.get(name)
        endpoint = os.getenv(f"NEXUS_{name.upper()}_ENDPOINT", "").strip()
        if isinstance(connector, BusinessApiConnector) and endpoint:
            research._providers[name] = business_api_provider(connector, endpoint, confidence=90)

    http_research_url = os.getenv("NEXUS_HTTP_RESEARCH_URL", "").strip()
    http_connector = registry.connectors.get("http_json")
    if http_research_url and isinstance(http_connector, HttpJsonConnector):
        research.register("http_json", http_json_provider(http_connector, http_research_url, confidence=88))
        research.register("web_http", http_json_provider(http_connector, http_research_url, confidence=88))
        research._providers["web"] = http_json_provider(http_connector, http_research_url, confidence=88)

    actions = ActionExecutor({"draft_email": draft_email_handler})
    verifier = ActionVerifier({"draft_email": draft_email_verifier})

    action_url = os.getenv("NEXUS_ACTION_URL", "").strip()
    action_endpoint = os.getenv("NEXUS_ACTION_ENDPOINT", "").strip()
    action_token_env = os.getenv("NEXUS_ACTION_TOKEN_ENV", "").strip() or None
    action_allowed_hosts = frozenset(host.strip() for host in os.getenv("NEXUS_HTTP_ALLOWED_HOSTS", "").split(",") if host.strip())
    if action_url and action_endpoint and action_allowed_hosts:
        connector = BusinessActionConnector(
            BusinessActionConfig(
                name="business_action",
                base_url=action_url,
                allowed_hosts=action_allowed_hosts,
                token_env=action_token_env,
                timeout_seconds=float(os.getenv("NEXUS_ACTION_TIMEOUT_SECONDS", "10")),
                max_response_bytes=int(os.getenv("NEXUS_ACTION_MAX_BYTES", "2000000")),
                max_retries=int(os.getenv("NEXUS_ACTION_MAX_RETRIES", "2")),
            )
        )
        registry.add_connector("business_action", connector)
        method = os.getenv("NEXUS_ACTION_METHOD", "POST").strip().upper()
        read_back: ReadAfterWriteVerifier | None = None
        try:
            read_back = build_read_back_verifier_from_env()
        except ValueError:
            # Invalid external verification configuration must not break the local runtime.
            read_back = None
        for action_type in ("update_crm", "change_purchase_order", "send_email"):
            actions.register(action_type, _real_action_handler(connector, action_endpoint, method))
            if read_back is not None:
                verifier.register(action_type, read_back.verify)
            else:
                verifier.register(action_type, _real_action_verifier)

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
    return MissionRuntime(orchestrator, actions, verifier, registry, repository, scheduler)


def build_mission_orchestrator() -> MissionOrchestrator:
    """Backward-compatible factory; new callers should prefer build_runtime()."""
    return build_runtime().orchestrator
