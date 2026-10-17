from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SalaryInfo:
    minimum: float
    maximum: float | None
    currency: str
    period: str | None


_AMOUNT = r"(?:\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d{3,6}(?:[.,]\d{1,2})?|\d{1,2}(?:[.,]\d{1,2})?\s*k\b|\d+(?:[.,]\d{1,2})?)"
_CURR_PRE = r"(?P<currency>s\/\.?|\bsoles?\b|\bpen\b|\busd\b|\buss\b|\$)"
_CURR_OPT = r"(?:s\/\.?|\bsoles?\b|\bpen\b|\busd\b|\buss\b|\$)?"
_SEP = r"(?:[-–—]|(?:\ba\b|\by\b|\bhasta\b|\bal\b))"

# 1) Explicit currency before numbers: "S/ 1,200 a S/ 1,500", "entre S/ 1200 y 1500"
_RANGE_PRE = re.compile(
    rf"{_CURR_PRE}\s*(?P<min>{_AMOUNT})(?![\d.,])\s*{_SEP}\s*{_CURR_OPT}\s*(?P<max>{_AMOUNT})(?![\d.,])",
    re.IGNORECASE,
)
# 2) Explicit currency after numbers: "1,300 a 1,500 soles", "1200 soles"
_RANGE_POST = re.compile(
    rf"(?<![\d.,])(?P<min>{_AMOUNT})\s*{_SEP}\s*(?P<max>{_AMOUNT})\s*(?P<currency>\bsoles?\b|\bpen\b|\busd\b|\bd[oó]lares?\b)",
    re.IGNORECASE,
)
# 3) Salary keyword + numbers >= 930 even without S/: "Sueldo 1300 a 1500", "el sueldo es de 2000"
_KEYWORD_SALARY = re.compile(
    rf"\b(?:sueldos?|salarios?|remuneraci[oó]n(?:es)?|subvenci[oó]n(?:es)?|b[aá]sico\s+mensual|haber\s+b[aá]sico|estipendios?)\b"
    rf"[^.\n\d]{{0,28}}?(?P<currency>s\/\.?|\busd\b|\$)?\s*(?P<min>{_AMOUNT})(?![\d.,])"
    rf"(?:\s*{_SEP}\s*{_CURR_OPT}\s*(?P<max>{_AMOUNT})(?![\d.,]))?",
    re.IGNORECASE,
)
# 4) Explicit currency before single amount: "S/ 1,500"
_SINGLE_PRE = re.compile(rf"{_CURR_PRE}\s*(?P<min>{_AMOUNT})(?![\d.,])", re.IGNORECASE)
# 5) Explicit currency after single amount: "1,500 soles"
_SINGLE_POST = re.compile(
    rf"(?<![\d.,])(?P<min>{_AMOUNT})\s*(?P<currency>\bsoles?\b|\bpen\b|\busd\b|\bd[oó]lares?\b)",
    re.IGNORECASE,
)
# 6) Title range in parentheses: "(2300 a 2500)"
_TITLE_RANGE = re.compile(
    r"\(\s*(?:s\/\.?\s*)?(?P<min>[1-9]\d{3})\s*(?:[-–—]|\ba\b|\bhasta\b)\s*(?:s\/\.?\s*)?(?P<max>[1-9]\d{3})\s*\)",
    re.IGNORECASE,
)

_PERIOD = re.compile(
    r"\b(mensual(?:es)?|mes(?:es)?|quincenal(?:es)?|semanal(?:es)?|diari(?:o|a|os|as)|horas?|anual(?:es)?)\b",
    re.IGNORECASE,
)
_NON_SALARY_AFTER = re.compile(
    r"^\s*(?:millones?|mill[oó]n|billions?|billones?|trillions?|mm\b|m\b|b\b|mil\s+millones|%|años?|meses|d[ií]as?|horas?|personas?|vacantes?|colaboradores?|clientes?|usuarios?|tiendas?|plantas?|pa[ií]ses?| sedes?\b)",
    re.IGNORECASE,
)
_BONUS_CONTEXT = re.compile(
    r"\b(?:bono|movilidad|pasajes?|alimentaci[oó]n|alimentos?|asignaci[oó]n\s+familiar|tarjeta|provis|pluxee|edenred|sodexo|vales?|comisi[oó]n|utilidades|fallecimiento|c[oó]nyuge|refrig)\b",
    re.IGNORECASE,
)
_MAIN_SALARY_CONTEXT = re.compile(
    r"\b(?:sueldo|salario|remuneraci[oó]n|subvenci[oó]n|b[aá]sico|bruto|mensual|planilla|gana\s+hasta|ingreso)\b",
    re.IGNORECASE,
)
_ISO_NUMBERS = {9000, 9001, 14000, 14001, 18001, 19011, 22000, 26000, 27000, 27001, 31000, 37001, 45001, 50001}


def _clean_text(text: str) -> str:
    return (
        text.replace(r"\.", ".")
        .replace(r"\-", "-")
        .replace("\xa0", " ")
        .replace("\u202f", " ")
    )


def _number(value: str) -> float:
    raw = value.strip().lower()
    multiplier = 1.0
    if raw.endswith("k"):
        multiplier = 1000.0
        raw = raw[:-1].strip()
    if "." in raw and "," in raw:
        # Distinguish US/Peruvian "1,200.00" from European "1.200,00" by last separator
        if raw.rfind(".") > raw.rfind(","):
            raw = raw.replace(",", "")
        else:
            raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        parts = raw.split(",")
        raw = "".join(parts) if len(parts[-1]) == 3 else ".".join(parts)
    elif "." in raw:
        parts = raw.split(".")
        if len(parts) > 2 or len(parts[-1]) == 3:
            raw = "".join(parts)
    return float(raw) * multiplier


def _currency(value: str | None) -> str:
    if not value:
        return "PEN"
    low = value.strip().lower()
    return "USD" if low in {"usd", "uss", "$"} or low.startswith(("dól", "dol")) else "PEN"


def _is_plausible_amount(amount: float, currency: str, *, explicit_currency: bool) -> bool:
    if currency == "USD":
        return 300.0 <= amount <= 25_000.0
    if not explicit_currency:
        if int(amount) in _ISO_NUMBERS or (1990 <= int(amount) <= 2035 and int(amount) != 2000 and int(amount) != 2020):
            return False
        return 1000.0 <= amount <= 25_000.0
    return 500.0 <= amount <= 35_000.0


def _valid_candidate(
    text: str,
    match: re.Match[str],
    minimum: float,
    maximum: float | None,
    currency: str,
    *,
    explicit_currency: bool,
) -> SalaryInfo | None:
    after = text[match.end() : min(len(text), match.end() + 40)]
    if _NON_SALARY_AFTER.search(after):
        return None
    before_line = text[max(0, text.rfind("\n", 0, match.start()) + 1, match.start() - 60) : match.start()]
    # Ignore ISO / law / year references
    if re.search(r"\b(?:iso|ntp|nom|ohsas|ley|decreto|c[oó]digo|id|nro|n[°º]|año|egresad[oa]|promoci[oó]n)\s*$", before_line, re.IGNORECASE):
        return None
    # Ignore small allowances/bonuses when the line is talking about a bonus rather than base pay
    if minimum < 1000 and _BONUS_CONTEXT.search(before_line) and not _MAIN_SALARY_CONTEXT.search(before_line):
        return None
    if not _is_plausible_amount(minimum, currency, explicit_currency=explicit_currency):
        return None
    if maximum is not None:
        if maximum < minimum:
            minimum, maximum = maximum, minimum
        if not _is_plausible_amount(maximum, currency, explicit_currency=explicit_currency):
            return None
        if maximum > minimum * 4:
            return None
    period = _period_near_match(text, match)
    return SalaryInfo(minimum, maximum, currency, period)


def extract_salary(description: str | None, title: str | None = None) -> SalaryInfo | None:
    """Extrae el sueldo o rango salarial más plausible del título y la descripción.

    Ignora placeholders de portales (S/ 1, S/ 2), pasajes/bonos menores y cifras de facturación
    corporativa, priorizando rangos y montos >= S/ 1,000 (o >= S/ 500 si es part-time con moneda explícita).
    """
    combined = "\n".join(part for part in (title, description) if part)
    if not combined:
        return None
    text = _clean_text(combined)
    candidates: list[tuple[int, SalaryInfo]] = []

    # 1. Range patterns (highest priority when >= 1000)
    for pattern, explicit in ((_RANGE_PRE, True), (_RANGE_POST, True), (_TITLE_RANGE, False)):
        for match in pattern.finditer(text):
            curr = _currency(match.groupdict().get("currency"))
            info = _valid_candidate(
                text,
                match,
                _number(match.group("min")),
                _number(match.group("max")),
                curr,
                explicit_currency=explicit,
            )
            if info:
                priority = 4 if info.minimum >= 1000 else 2
                candidates.append((priority, info))

    # 2. Keyword-anchored salary (e.g. "Sueldo: 1300 a 1500", "Remuneración mensual S/ 2,000")
    for match in _KEYWORD_SALARY.finditer(text):
        has_curr = bool(match.group("currency"))
        curr = _currency(match.group("currency"))
        max_str = match.group("max")
        info = _valid_candidate(
            text,
            match,
            _number(match.group("min")),
            _number(max_str) if max_str else None,
            curr,
            explicit_currency=has_curr,
        )
        if info:
            priority = (4 if info.maximum is not None else 3) if info.minimum >= 1000 else 1
            candidates.append((priority, info))

    # 3. Single explicit currency patterns ("S/ 1,500", "1,500 soles")
    for pattern in (_SINGLE_PRE, _SINGLE_POST):
        for match in pattern.finditer(text):
            curr = _currency(match.group("currency"))
            info = _valid_candidate(
                text,
                match,
                _number(match.group("min")),
                None,
                curr,
                explicit_currency=True,
            )
            if info:
                priority = 3 if info.minimum >= 1000 else 1
                candidates.append((priority, info))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _period_near_match(description: str, match: re.Match[str]) -> str | None:
    """Read the salary period only from the nearby salary line."""
    line_end = description.find("\n", match.end())
    end_limit = min(len(description), match.end() + 80) if line_end == -1 else min(line_end, match.end() + 80)
    after = description[match.end() : end_limit]
    period_match = _PERIOD.search(after)
    if not period_match:
        line_start = description.rfind("\n", 0, match.start())
        start_limit = max(0, match.start() - 50) if line_start == -1 else max(line_start + 1, match.start() - 50)
        before = description[start_limit : match.start()]
        period_match = _PERIOD.search(before)
    return period_match.group(1).lower() if period_match else None
