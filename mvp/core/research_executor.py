from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

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
