from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SalaryInfo:
    minimum: float
    maximum: float | None
    currency: str
    period: str | None


_AMOUNT = r"\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_RANGE = re.compile(
    rf"(?P<currency>s\/\.?|soles?|pen|usd|\$)\s*(?P<min>{_AMOUNT})(?![\d.,])\s*(?:[-–—]|a|hasta)\s*(?:s\/\.?|soles?|pen|usd|\$)?\s*(?P<max>{_AMOUNT})(?![\d.,])",
    re.IGNORECASE,
)
_SINGLE = re.compile(rf"(?P<currency>s\/\.?|soles?|pen|usd|\$)\s*(?P<min>{_AMOUNT})(?![\d.,])", re.IGNORECASE)
_PERIOD = re.compile(
    r"\b(mensual(?:es)?|mes(?:es)?|quincenal(?:es)?|semanal(?:es)?|diari(?:o|a|os|as)|horas?|anual(?:es)?)\b",
    re.IGNORECASE,
)


def _number(value: str) -> float:
    value = value.strip()
    if "." in value and "," in value:
        value = value.replace(".", "").replace(",", ".")
    elif "," in value:
        parts = value.split(",")
        value = "".join(parts) if len(parts[-1]) == 3 else ".".join(parts)
    elif "." in value and len(value.rsplit(".", 1)[-1]) == 3:
        value = value.replace(".", "")
    return float(value)


def _currency(value: str) -> str:
    return "USD" if value.lower() in {"usd", "$"} else "PEN"


def extract_salary(description: str | None) -> SalaryInfo | None:
    """Extrae rangos conservadores; solo acepta moneda explícita para evitar falsos positivos."""
    if not description:
        return None
    match = _RANGE.search(description)
    if match:
        return SalaryInfo(
            _number(match.group("min")),
            _number(match.group("max")),
            _currency(match.group("currency")),
            _period_near_match(description, match),
        )
    match = _SINGLE.search(description)
    if match:
        return SalaryInfo(
            _number(match.group("min")), None, _currency(match.group("currency")), _period_near_match(description, match)
        )
    return None


def _period_near_match(description: str, match: re.Match[str]) -> str | None:
    """Read the salary period only from the nearby salary line."""
    after = description[match.end() : min(len(description), match.end() + 80)]
    period_match = _PERIOD.search(after)
    if not period_match:
        before = description[max(0, match.start() - 50) : match.start()]
        period_match = _PERIOD.search(before)
    return period_match.group(1).lower() if period_match else None
