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


def reason_from_evidence(goal: str, constraints: list[str], context: BusinessContext) -> EvidenceDecision:
    """Produce a conservative decision whose confidence is grounded in collected evidence."""
    evidence = list(context.evidence.values())
    score = _evidence_score(evidence)
    ids = [item.id for item in evidence]
    cost_goal = any(token in goal.lower() for token in ("cost", "تكلفة", "مصروف", "مصاريف", "خفض"))

    if cost_goal:
        rationale = []
        for item in evidence[:5]:
            rationale.append(f"{item.claim}: {item.value}")
        if not rationale:
            rationale.append("لا توجد أدلة كافية مرتبطة بالهدف.")
        confidence = min(95, max(35, score if evidence else 35))
        return EvidenceDecision(
            title="قرار مبني على الأدلة الحالية",
            summary="تم ربط الهدف بالأدلة التي جُمعت وتحديد التدخل الأقل مخاطرة المتاح حاليًا.",
            priority="high" if confidence >= 75 else "medium",
            confidence=confidence,
            rationale=rationale,
            recommended_action="إعداد مسودة تفاوض ومراجعتها قبل أي التزام مالي أو تعاقدي.",
            expected_impact="تقليل التكلفة المحتملة مع إبقاء القرار تحت اعتماد بشري.",
            evidence_ids=ids,
            evidence_count=len(evidence),
            evidence_confidence=score,
        )

    confidence = min(90, max(35, score if evidence else 35))
    return EvidenceDecision(
        title="قرار أولي مبني على السياق المتاح",
        summary="تم تحليل الأدلة المتاحة دون تجاوز ما تثبته البيانات.",
        priority="medium",
        confidence=confidence,
        rationale=[f"{item.claim}: {item.value}" for item in evidence[:5]] or ["لا توجد أدلة كافية لاتخاذ قرار قوي."],
        recommended_action="مراجعة التدخل المقترح واعتماد خطوة قابلة للقياس.",
        expected_impact="تحويل الأدلة الحالية إلى إجراء يمكن التحقق من أثره.",
        evidence_ids=ids,
        evidence_count=len(evidence),
        evidence_confidence=score,
    )
