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
class GoalProfile:
    """Stable business intent classification shared across planning stages."""

    key: str
    label: str
    evidence_domains: tuple[str, ...]
    action_posture: str


@dataclass(frozen=True, slots=True)
class ResearchNeed:
    """A category of evidence required to reason about a goal."""

    domain: str
    reason: str
    priority: int = 50


@dataclass(slots=True)
class GoalPlan:
    goal: Goal
    profile: GoalProfile
    research_needs: list[ResearchNeed] = field(default_factory=list)

    def domains(self) -> list[str]:
        return [item.domain for item in sorted(self.research_needs, key=lambda item: (-item.priority, item.domain))]


_PROFILES = {
    "cost": GoalProfile(
        "cost", "خفض التكلفة", ("operations", "suppliers", "contracts"), "negotiate_before_commit",
    ),
    "revenue": GoalProfile(
        "revenue", "نمو الإيرادات", ("customers", "sales_pipeline", "channels"), "experiment_before_scale",
    ),
    "risk": GoalProfile(
        "risk", "خفض المخاطر", ("regulatory", "operations"), "treat_before_change",
    ),
    "customer": GoalProfile(
        "customer", "تحسين العملاء", ("customers", "sales_pipeline"), "measure_before_rollout",
    ),
    "supplier": GoalProfile(
        "supplier", "تحسين الموردين", ("suppliers", "contracts"), "review_before_contract_change",
    ),
    "general": GoalProfile(
        "general", "هدف أعمال عام", ("business_context",), "measure_before_action",
    ),
}


def classify_goal(text: str) -> GoalProfile:
    """Classify intent once so planning and reasoning share the same goal vocabulary."""
    normalized = " ".join(text.lower().split())
    if any(token in normalized for token in ("cost", "تكلفة", "مصروف", "مصاريف", "خفض", "خفض التكاليف", "هامش")):
        return _PROFILES["cost"]
    if any(token in normalized for token in ("sales", "revenue", "ربح", "إيراد", "مبيعات", "نمو المبيعات")):
        return _PROFILES["revenue"]
    if any(token in normalized for token in ("risk", "compliance", "خطر", "مخاطر", "مخاطرة", "امتثال", "تنظيم")):
        return _PROFILES["risk"]
    if any(token in normalized for token in ("customer", "retention", "تجربة العملاء", "العملاء", "احتفاظ")):
        return _PROFILES["customer"]
    if any(token in normalized for token in ("supplier", "vendor", "مورد", "موردين")):
        return _PROFILES["supplier"]
    return _PROFILES["general"]


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
    profile = classify_goal(goal.objective)
    reasons = {
        "operations": "قياس أين تتكون التكلفة أو التعرض داخل العملية",
        "suppliers": "فحص تغيرات الشراء والتوريد والبدائل",
        "contracts": "فحص الالتزامات والقيود التعاقدية",
        "customers": "فحص سلوك العملاء والفرص الحالية",
        "sales_pipeline": "فحص مراحل الصفقات وأسباب التعثر",
        "channels": "فحص أداء قنوات الاستحواذ والتحويل",
        "regulatory": "فحص المتطلبات والتغيرات الرسمية ذات الصلة",
        "business_context": "تكوين سياق أولي قبل تحديد مصادر أعمق",
    }
    priorities = {
        "operations": 95,
        "suppliers": 90,
        "contracts": 85,
        "customers": 95,
        "sales_pipeline": 90,
        "channels": 80,
        "regulatory": 95,
        "business_context": 70,
    }
    needs = [
        ResearchNeed(domain, reasons[domain], priorities[domain])
        for domain in profile.evidence_domains
    ]
    return GoalPlan(goal=goal, profile=profile, research_needs=needs)
