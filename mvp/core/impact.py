from __future__ import annotations

from dataclasses import dataclass

from .change_detector import Change
from .goal_planner import Goal, ResearchNeed


@dataclass(frozen=True, slots=True)
class ImpactAssessment:
    key: str
    score: int
    relevant: bool
    reason: str


def assess_change(change: Change, goal: Goal, needs: list[ResearchNeed]) -> ImpactAssessment:
    """Estimate whether a change is worth surfacing for the active goal.

    This is a deliberately conservative heuristic layer. It is independent
    from connectors and can later be replaced by a learned/model-based scorer.
    """
    text = f"{change.key} {change.current}".lower()
    domains = " ".join(item.domain for item in needs).lower()
    score = 20
    reasons: list[str] = []

    if change.kind == "updated":
        score += 25
        reasons.append("القيمة تغيّرت منذ آخر ملاحظة")
    elif change.kind == "new":
        score += 10
        reasons.append("هذه إشارة جديدة على الذاكرة")

    keyword_groups = {
        "suppliers": ("supplier", "vendor", "مورد"),
        "contracts": ("contract", "agreement", "عقد"),
        "operations": ("cost", "spend", "amount", "تكلفة", "مصروف", "إنفاق"),
        "customers": ("customer", "client", "عميل"),
        "sales_pipeline": ("deal", "pipeline", "sales", "صفقة", "مبيعات"),
        "regulatory": ("regulation", "compliance", "regulatory", "امتثال", "تنظيم"),
    }
    for domain, keywords in keyword_groups.items():
        if domain in domains and any(word in text for word in keywords):
            score += 25
            reasons.append(f"مرتبطة مباشرة بمسار البحث: {domain}")

    if goal.target_value is not None and isinstance(change.current, (int, float)):
        distance = abs(float(change.current) - goal.target_value)
        if distance > 0:
            score += 10
            reasons.append("القيمة تختلف عن الهدف الرقمي المحدد")

    score = min(score, 100)
    relevant = score >= 55
    if not reasons:
        reasons.append("لا توجد صلة قوية كافية بالهدف الحالي")
    return ImpactAssessment(
        key=change.key,
        score=score,
        relevant=relevant,
        reason="؛ ".join(reasons),
    )
