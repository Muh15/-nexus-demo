from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from connectors.http_json_connector import HttpJsonConnector

from .models import BusinessContext, Evidence
from .research_planner import ResearchPlan, ResearchTask


@dataclass(frozen=True, slots=True)
class ResearchResult:
    task_domain: str
    connector: str
    status: str
    evidence: list[Evidence] = field(default_factory=list)
    message: str = ""


ResearchProvider = Callable[[ResearchTask, BusinessContext], ResearchResult]


class ResearchExecutor:
    """Executes planned research through replaceable domain providers."""

    def __init__(self, providers: dict[str, ResearchProvider] | None = None) -> None:
        self._providers = dict(providers or {})

    def register(self, name: str, provider: ResearchProvider) -> None:
        if name in self._providers:
            raise ValueError(f"research provider already registered: {name}")
        self._providers[name] = provider

    def execute(self, plan: ResearchPlan, context: BusinessContext) -> list[ResearchResult]:
        results: list[ResearchResult] = []
        for task in plan.pending():
            provider = self._providers.get(task.connector)
            if provider is None:
                results.append(
                    ResearchResult(
                        task_domain=task.domain,
                        connector=task.connector,
                        status="unavailable",
                        message="No provider is registered for this connector.",
                    )
                )
                continue
            results.append(provider(task, context))
        return results


def context_provider(connector: str, source: str, confidence: int = 80) -> ResearchProvider:
    """Build a deterministic local provider for MVP tests and safe demos."""

    def provide(task: ResearchTask, context: BusinessContext) -> ResearchResult:
        evidence = [
            Evidence(
                id=f"research:{task.domain}:{index}",
                source=source,
                claim=task.question,
                value=item.value,
                confidence=confidence,
                locator=item.locator,
                metadata={"domain": task.domain, "connector": connector, "task": task.reason},
            )
            for index, item in enumerate(context.evidence.values(), start=1)
        ]
        return ResearchResult(
            task_domain=task.domain,
            connector=connector,
            status="completed",
            evidence=evidence,
            message=f"Reused {len(evidence)} existing evidence items as MVP research input.",
        )

    return provide


def http_json_provider(
    connector: HttpJsonConnector,
    url: str,
    *,
    confidence: int = 88,
    headers: dict[str, str] | None = None,
) -> ResearchProvider:
    """Build a research provider backed by an allow-listed JSON HTTP source."""

    endpoint = url.strip()
    if not endpoint:
        raise ValueError("HTTP research URL is required")

    def provide(task: ResearchTask, context: BusinessContext) -> ResearchResult:
        del context
        try:
            result = connector.fetch(endpoint, headers=headers)
        except Exception as exc:
            return ResearchResult(
                task_domain=task.domain,
                connector=task.connector,
                status="unavailable",
                message=f"HTTP research failed: {exc}",
            )

        evidence = [
            Evidence(
                id=f"research:http:{task.domain}:{index}",
                source="http_json",
                claim=task.question,
                value=record,
                confidence=confidence,
                locator=provenance.get("locator"),
                metadata={
                    "domain": task.domain,
                    "connector": task.connector,
                    "task": task.reason,
                    "url": endpoint,
                    "sha256": result.metadata.get("sha256"),
                    "status_code": result.metadata.get("status_code"),
                },
            )
            for index, (record, provenance) in enumerate(
                zip(result.records, result.provenance or [{} for _ in result.records]), start=1
            )
        ]
        return ResearchResult(
            task_domain=task.domain,
            connector=task.connector,
            status="completed",
            evidence=evidence,
            message=f"Collected {len(evidence)} records from the configured HTTP JSON source.",
        )

    return provide
