from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import BusinessContext, Evidence


@dataclass(frozen=True, slots=True)
class EvidenceDecision:
    title: str
    summary: str
    priority: str
    confidence: int
    rationale: list[str]
    recommended_action: str
    expected_impact: str
    evidence_ids: list[str]
    evidence_count: int
    evidence_confidence: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "priority": self.priority,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "recommended_action": self.recommended_action,
            "expected_impact": self.expected_impact,
            "evidence_ids": self.evidence_ids,
            "evidence_count": self.evidence_count,
            "evidence_confidence": self.evidence_confidence,
        }


def _evidence_score(items: list[Evidence]) -> int:
    if not items:
        return 0
    return round(sum(max(0, min(100, item.confidence)) for item in items) / len(items))


def _goal_profile(goal: str) -> str:
    text = goal.lower()
    if any(token in text for token in ("cost", "تكلفة", "مصروف", "مصاريف", "خفض", "خفض التكاليف")):
        return "cost"
    if any(token in text for token in ("revenue", "sales", "ربح", "إيراد", "مبيعات", "نمو المبيعات")):
        return "revenue"
    if any(token in text for token in ("risk", "compliance", "مخاطر", "مخاطرة", "امتثال", "تنظيم")):
        return "risk"
    if any(token in text for token in ("customer", "retention", "تجربة العملاء", "العملاء", "احتفاظ")):
        return "customer"
    if any(token in text for token in ("supplier", "vendor", "مورد", "موردين")):
        return "supplier"
    return "general"


def reason_from_evidence(goal: str, constraints: list[str], context: BusinessContext) -> EvidenceDecision:
    """Produce a conservative, goal-profiled decision grounded in collected evidence."""
    evidence = list(context.evidence.values())
    score = _evidence_score(evidence)
    ids = [item.id for item in evidence]
    rationale = [f"{item.claim}: {item.value}" for item in evidence[:5]] or ["لا توجد أدلة كافية لاتخاذ قرار قوي."]
    confidence = min(95, max(35, score if evidence else 35))
    profile = _goal_profile(goal)

    profiles = {
        "cost": (
            "قرار خفض التكلفة مبني على الأدلة",
            "تم ربط هدف خفض التكلفة بالأدلة الحالية وتحديد تدخل منخفض المخاطر قبل أي التزام.",
            "إعداد مسودة تفاوض ومراجعتها قبل أي التزام مالي أو تعاقدي.",
            "تقليل التكلفة المحتملة مع إبقاء القرار تحت اعتماد بشري.",
        ),
        "revenue": (
            "قرار نمو إيرادات مبني على الأدلة",
            "تم ربط هدف النمو التجاري بالإشارات الحالية وتحديد تجربة قابلة للقياس قبل التوسع.",
            "إعداد خطة تجربة مبيعات محدودة ومراجعتها قبل إطلاقها على نطاق واسع.",
            "رفع الإيرادات المحتملة مع حصر المخاطرة في تجربة قابلة للقياس.",
        ),
        "risk": (
            "قرار خفض المخاطر مبني على الأدلة",
            "تم تحديد إشارات المخاطر وربطها بالهدف مع إبقاء التدخل ضمن حدود الاعتماد البشري.",
            "إعداد خطة معالجة للمخاطر وتحديد مالك وموعد مراجعة قبل تنفيذ أي تغيير حساس.",
            "تقليل التعرض للمخاطر وتحسين قابلية المتابعة والتحقق.",
        ),
        "customer": (
            "قرار تحسين العملاء مبني على الأدلة",
            "تم ربط هدف العملاء بالإشارات المتاحة واختيار تدخل صغير قابل للقياس قبل التوسع.",
            "إعداد تجربة تحسين لخدمة العملاء ومراجعة أثرها قبل تعميمها.",
            "تحسين تجربة العملاء مع قياس النتيجة قبل التوسع.",
        ),
        "supplier": (
            "قرار الموردين مبني على الأدلة",
            "تم ربط هدف الموردين بالأدلة الحالية وتحديد خطوة تفاوض أو مراجعة قابلة للتحقق.",
            "إعداد مراجعة للمورد وشروطه ومسودة تفاوض قبل أي تغيير تعاقدي.",
            "تحسين شروط المورد مع إبقاء الالتزام التعاقدي تحت اعتماد بشري.",
        ),
        "general": (
            "قرار أولي مبني على السياق المتاح",
            "تم تحليل الأدلة المتاحة دون تجاوز ما تثبته البيانات.",
            "مراجعة التدخل المقترح واعتماد خطوة قابلة للقياس.",
            "تحويل الأدلة الحالية إلى إجراء يمكن التحقق من أثره.",
        ),
    }
    title, summary, recommended_action, expected_impact = profiles[profile]
    priority = "high" if confidence >= 75 and profile != "general" else "medium"

    return EvidenceDecision(
        title=title,
        summary=summary,
        priority=priority,
        confidence=confidence,
        rationale=rationale,
        recommended_action=recommended_action,
        expected_impact=expected_impact,
        evidence_ids=ids,
        evidence_count=len(evidence),
        evidence_confidence=score,
    )
