from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .change_detector import Change, detect_record_changes
from .goal_planner import GoalPlan, build_goal_plan, parse_goal
from .impact import ImpactAssessment, assess_change
from .memory import MemoryStore


@dataclass(slots=True)
class MissionIntelligence:
    """Composable pre-reasoning layer for goal-aware signal selection."""

    memory: MemoryStore = field(default_factory=MemoryStore)

    def prepare(
        self,
        *,
        tenant_id: str,
        goal_text: str,
        constraints: Iterable[str] = (),
        records: list[dict[str, Any]] | None = None,
        source: str = "unknown",
    ) -> tuple[GoalPlan, list[Change], list[ImpactAssessment]]:
        goal = parse_goal(goal_text, list(constraints))
        plan = build_goal_plan(goal)
        changes = detect_record_changes(
            self.memory,
            tenant_id,
            list(records or []),
            source=source,
        )
        assessments = [assess_change(change, goal, plan.research_needs) for change in changes]
        assessments.sort(key=lambda item: (-item.score, item.key))
        return plan, changes, assessments

    @staticmethod
    def relevant_changes(assessments: list[ImpactAssessment]) -> list[ImpactAssessment]:
        return [item for item in assessments if item.relevant]
