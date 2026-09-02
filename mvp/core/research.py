from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .goal_planner import GoalPlan, ResearchNeed
from .models import Evidence


@dataclass(frozen=True, slots=True)
class ResearchTask:
    id: str
    domain: str
    reason: str
    priority: int
    provider: str


@dataclass(frozen=True, slots=True)
class ResearchResult:
    task_id: str
    provider: str
    domain: str
    records: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    status: str = "completed"
    message: str = ""


@dataclass(slots=True)
class ResearchPlan:
    tasks: list[ResearchTask] = field(default_factory=list)

    def pending(self) -> list[ResearchTask]:
        return [task for task in self.tasks]


Provider = Callable[[ResearchTask], ResearchResult]


class ResearchEngine:
    """Plans and executes narrowly-scoped research without owning domain logic."""

    def __init__(self, providers: dict[str, Provider] | None = None) -> None:
        self._providers = dict(providers or {})

    def register(self, name: str, provider: Provider) -> None:
        if name in self._providers:
            raise ValueError(f"research provider already registered: {name}")
        self._providers[name] = provider

    def plan(self, goal_plan: GoalPlan) -> ResearchPlan:
        tasks = [
            ResearchTask(
                id=f"research-{index:03d}",
                domain=need.domain,
                reason=need.reason,
                priority=need.priority,
                provider=self._provider_for(need.domain),
            )
            for index, need in enumerate(
                sorted(goal_plan.research_needs, key=lambda item: (-item.priority, item.domain)),
                start=1,
            )
        ]
        return ResearchPlan(tasks=tasks)

    def execute(self, plan: ResearchPlan) -> list[ResearchResult]:
        results: list[ResearchResult] = []
        for task in plan.pending():
            provider = self._providers.get(task.provider)
            if provider is None:
                results.append(
                    ResearchResult(
                        task_id=task.id,
                        provider=task.provider,
                        domain=task.domain,
                        status="unavailable",
                        message="No provider registered for this research domain.",
                    )
                )
                continue
            results.append(provider(task))
        return results

    def _provider_for(self, domain: str) -> str:
        if domain in self._providers:
            return domain
        if "business_context" in self._providers:
            return "business_context"
        return domain


def synthetic_provider(domain: str, records: Iterable[dict[str, Any]]) -> Provider:
    """Create a deterministic provider for local MVP/demo evidence."""

    snapshot = [dict(record) for record in records]

    def provide(task: ResearchTask) -> ResearchResult:
        evidence = [
            Evidence(
                id=f"research:{task.id}:{index}",
                source=task.provider,
                claim=f"research:{task.domain}",
                value=record,
                confidence=82,
                metadata={"task_id": task.id, "domain": task.domain},
            )
            for index, record in enumerate(snapshot, start=1)
        ]
        return ResearchResult(
            task_id=task.id,
            provider=task.provider,
            domain=domain,
            records=[dict(record) for record in snapshot],
            evidence=evidence,
            message=f"Collected {len(snapshot)} local MVP records.",
        )

    return provide
