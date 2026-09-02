from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .goal_planner import GoalPlan
from .impact import ImpactAssessment
from .models import BusinessContext


@dataclass(slots=True)
class ResearchTask:
    """A concrete information gap that must be closed before a decision."""

    domain: str
    question: str
    reason: str
    priority: int
    connector: str
    status: str = "planned"


@dataclass(slots=True)
class ResearchPlan:
    """Adaptive evidence-collection plan produced before reasoning."""

    tasks: list[ResearchTask] = field(default_factory=list)

    def pending(self) -> list[ResearchTask]:
        return [task for task in self.tasks if task.status == "planned"]

    def domains(self) -> list[str]:
        return [task.domain for task in self.tasks]


_CONNECTORS = {
    "suppliers": "supplier",
    "contracts": "contract",
    "operations": "erp",
    "customers": "crm",
    "sales_pipeline": "crm",
    "channels": "market",
    "regulatory": "web",
    "business_context": "file",
}

_QUESTIONS = {
    "suppliers": "ما تغيّر في أسعار وشروط الموردين المرتبطين بالهدف؟",
    "contracts": "ما الالتزامات والنوافذ التعاقدية التي قد تقيد القرار؟",
    "operations": "ما بنود التشغيل التي تتحرك بما يؤثر على الهدف؟",
    "customers": "ما تغيّر في العملاء بما يؤثر على تحقيق الهدف؟",
    "sales_pipeline": "ما حالة فرص المبيعات التي يمكن أن تحرك النتيجة؟",
    "channels": "ما تغيّر في السوق أو القنوات ذات الصلة؟",
    "regulatory": "هل توجد متطلبات أو تغيّرات تنظيمية تؤثر على القرار؟",
    "business_context": "ما البيانات الأساسية الناقصة لفهم الهدف قبل اتخاذ القرار؟",
}


def build_research_plan(
    goal_plan: GoalPlan,
    context: BusinessContext,
    assessments: Iterable[ImpactAssessment] = (),
) -> ResearchPlan:
    """Identify evidence gaps from the goal, current context, and impact signals."""
    assessments = list(assessments)
    by_domain = {item.key.split(":", 1)[0] for item in assessments if item.relevant}
    tasks: list[ResearchTask] = []

    for need in goal_plan.research_needs:
        domain = need.domain
        has_entities = any(
            entity.type == domain or domain in entity.attributes.get("domains", [])
            for entity in context.entities.values()
        )
        has_evidence = any(
            domain in (evidence.source or "").lower() or domain in str(evidence.claim).lower()
            for evidence in context.evidence.values()
        )
        impacted = domain in by_domain

        if not has_entities and not has_evidence:
            priority = min(100, need.priority + (15 if impacted else 0))
            tasks.append(
                ResearchTask(
                    domain=domain,
                    question=_QUESTIONS.get(domain, f"ما المعلومات الناقصة في نطاق {domain}؟"),
                    reason=f"لا توجد أدلة كافية حاليًا في نطاق {domain} لتحقيق الهدف.",
                    priority=priority,
                    connector=_CONNECTORS.get(domain, "file"),
                )
            )

    tasks.sort(key=lambda item: (-item.priority, item.domain))
    return ResearchPlan(tasks=tasks)
