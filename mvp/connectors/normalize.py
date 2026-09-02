from __future__ import annotations

import re
from typing import Any


ALIASES = {
    "supplier": {"supplier", "vendor", "المورد", "اسم المورد"},
    "monthly_spend": {"monthly_spend", "monthly spend", "spend", "الانفاق الشهري", "الإنفاق الشهري"},
    "price_change_pct": {"price_change", "price change", "price_change_pct", "نسبة الزيادة", "تغير السعر"},
    "contract_days_left": {"contract_days_left", "contract days left", "أيام العقد", "العقد"},
    "market_delta_pct": {"market_delta", "market delta", "market_delta_pct", "تغير السوق"},
}


def _key(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower().replace("_", " "))


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Convert common export labels into the NEXUS canonical signal fields."""
    normalized: dict[str, Any] = {}
    for raw_key, value in record.items():
        key = _key(raw_key)
        canonical = next((name for name, aliases in ALIASES.items() if key in {_key(a) for a in aliases}), None)
        normalized[canonical or key.replace(" ", "_")] = value

    for numeric in ("monthly_spend", "price_change_pct", "contract_days_left", "market_delta_pct"):
        if numeric in normalized:
            normalized[numeric] = _to_number(normalized[numeric])
    return normalized


def normalize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_record(record) for record in records]


def _to_number(value: Any) -> Any:
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip().replace(",", "")
    text = text.replace("%", "")
    try:
        return float(text) if "." in text else int(text)
    except ValueError:
        return value
