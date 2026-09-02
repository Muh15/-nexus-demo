from __future__ import annotations

from dataclasses import dataclass, field
import re


@dataclass(frozen=True, slots=True)
class Goal:
    """Normalized business goal kept independent from any specific domain."""

    raw: str
    objective: str
    horizon: str | None = None
    target_value: float | None = None
    target_unit: str | None = None
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResearchNeed:
    """A category of evidence required to reason about a goal."""

    domain: str
    reason: str
    priority: int = 50


@dataclass(slots=True)
class GoalPlan:
    goal: Goal
    research_needs: list[ResearchNeed] = field(default_factory=list)

    def domains(self) -> list[str]:
        return [item.domain for item in sorted(self.research_needs, key=lambda item: (-item.priority, item.domain))]


def parse_goal(raw: str, constraints: list[str] | None = None) -> Goal:
    """Extract only high-confidence structure; leave ambiguous wording intact."""
    text = " ".join(raw.split()).strip()
    match = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*(%|ريال|SAR|days?|days|يوم|أيام|month|months|أشهر|سنة|سنوات)?", text, re.IGNORECASE)
    value = float(match.group(1).replace(",", "")) if match else None
    unit = match.group(2) if match and match.group(2) else None
    horizon = None
    horizon_match = re.search(r"(?:within|خلال|في غضون)\s+([^,.]+)", text, re.IGNORECASE)
    if horizon_match:
        horizon = horizon_match.group(1).strip()
    return Goal(
        raw=raw,
        objective=text,
        horizon=horizon,
        target_value=value,
        target_unit=unit,
        constraints=tuple(constraints or ()),
    )


def build_goal_plan(goal: Goal) -> GoalPlan:
    """Infer what NEXUS may need to observe without hard-coding connectors."""
    text = goal.objective.lower()
    needs: list[ResearchNeed] = []

    if any(token in text for token in ("cost", "تكلفة", "مصروف", "مصاريف", "خفض", "هامش")):
        needs.extend([
            ResearchNeed("operations", "قياس أين تتكون التكلفة داخل العملية", 95),
            ResearchNeed("suppliers", "فحص تغيرات الشراء والتوريد والبدائل", 90),
            ResearchNeed("contracts", "فحص الالتزامات والقيود التعاقدية", 85),
        ])

    if any(token in text for token in ("sales", "revenue", "مبيعات", "إيرادات", "نمو", "نمو المبيعات")):
        needs.extend([
            ResearchNeed("customers", "فحص سلوك العملاء والفرص الحالية", 95),
            ResearchNeed("sales_pipeline", "فحص مراحل الصفقات وأسباب التعثر", 90),
            ResearchNeed("channels", "فحص أداء قنوات الاستحواذ والتحويل", 80),
        ])

    if any(token in text for token in ("risk", "خطر", "مخاطر", "امتثال", "compliance")):
        needs.extend([
            ResearchNeed("regulatory", "فحص المتطلبات والتغيرات الرسمية ذات الصلة", 95),
            ResearchNeed("operations", "فحص نقاط التعرض داخل العمليات", 85),
        ])

    if not needs:
        needs.append(ResearchNeed("business_context", "تكوين سياق أولي قبل تحديد مصادر أعمق", 70))

    return GoalPlan(goal=goal, research_needs=needs)
