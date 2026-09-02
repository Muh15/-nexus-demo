from __future__ import annotations

import hashlib
from typing import Any, Iterable

from .models import BusinessContext, Entity, Evidence, Relationship


ALIASES = {
    "supplier": {"supplier", "vendor", "provider", "المورد", "اسم المورد"},
    "contract": {"contract", "contract_id", "agreement", "العقد", "رقم العقد"},
    "customer": {"customer", "client", "العميل"},
    "amount": {"amount", "spend", "monthly_spend", "cost", "المبلغ", "التكلفة"},
}


def _key(value: Any) -> str:
    return str(value).strip().lower()


def _find_value(record: dict[str, Any], aliases: set[str]) -> Any:
    for key, value in record.items():
        if _key(key) in aliases and value not in (None, ""):
            return value
    return None


def build_context(records: Iterable[dict[str, Any]], *, source: str = "unknown") -> BusinessContext:
    """Turn loosely shaped connector rows into traceable business context.

    This is intentionally conservative: it creates only high-confidence
    entities from recognizable fields. Ambiguous fields remain as evidence
    instead of being silently assigned a business meaning.
    """
    context = BusinessContext()

    for index, record in enumerate(records, start=1):
        supplier = _find_value(record, ALIASES["supplier"])
        contract = _find_value(record, ALIASES["contract"])
        customer = _find_value(record, ALIASES["customer"])
        amount = _find_value(record, ALIASES["amount"])

        entity_ids: list[str] = []
        if supplier is not None:
            supplier_id = f"supplier:{_key(supplier)}"
            context.add_entity(Entity(supplier_id, "supplier", str(supplier)))
            entity_ids.append(supplier_id)
        if contract is not None:
            contract_id = f"contract:{_key(contract)}"
            context.add_entity(Entity(contract_id, "contract", str(contract)))
            entity_ids.append(contract_id)
        if customer is not None:
            customer_id = f"customer:{_key(customer)}"
            context.add_entity(Entity(customer_id, "customer", str(customer)))
            entity_ids.append(customer_id)

        raw = repr(sorted(record.items())).encode("utf-8")
        evidence_id = f"ev:{hashlib.sha256(raw).hexdigest()[:16]}"
        evidence = Evidence(
            id=evidence_id,
            source=source,
            claim="connector_record",
            value=record,
            confidence=90 if entity_ids else 60,
            locator=f"record:{index}",
        )
        context.add_evidence(evidence)

        if supplier is not None and contract is not None:
            context.link(Relationship(
                source_id=f"supplier:{_key(supplier)}",
                relation="governed_by",
                target_id=f"contract:{_key(contract)}",
                confidence=96,
                evidence_ids=[evidence_id],
            ))

        if supplier is not None and amount is not None:
            context.entities[f"supplier:{_key(supplier)}"].attributes.setdefault("amounts", []).append(amount)

    return context
