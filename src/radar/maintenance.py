"""Mantenimiento de la clasificación: auditar si las áreas guardadas coinciden con las reglas vigentes
y, con confirmación, reclasificar. Nunca borra ofertas; antes de escribir guarda una copia reversible."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from radar.careers import active_pack
from radar.classify import classify
from radar.db.database import connection, database_path
from radar.db.repository import _write_areas, recompute_scores
from radar.domain.models import RawJob
from radar.settings import get_setting, set_setting
from radar.taxonomy import infer_relevance

RULES_KEY = "classification_rules_hash"


def rules_fingerprint(pack=None) -> str:
    """Huella de las reglas que deciden áreas y relevancia; cambia cuando se editan."""
    pack = pack or active_pack()
    payload = json.dumps([pack.id, sorted(pack.core_areas), sorted(pack.adjacent_areas), pack.area_rules,
                          pack.out_of_focus_rules, sorted(pack.weak_terms), pack.excluded_title_signals],
                         ensure_ascii=False, sort_keys=True, default=list)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def rules_stale() -> bool:
    """True si las reglas cambiaron desde la última reclasificación (o nunca se registró)."""
    return get_setting(RULES_KEY) != rules_fingerprint()


def _stored() -> list[tuple]:
    with connection() as conn:
        return conn.execute(
            """SELECT j.id, j.title, j.description_raw, j.location, co.name, ia.name, j.relevance_tier
            FROM jobs j LEFT JOIN companies co ON co.id=j.company_id
            LEFT JOIN job_areas ja ON ja.job_id=j.id AND ja.is_primary
            LEFT JOIN industrial_areas ia ON ia.id=ja.area_id"""
        ).fetchall()


def _reclassified(row: tuple, pack):
    raw = RawJob(source="audit", title=row[1], company=row[4], location=row[3], description=row[2], url="audit")
    classified = classify(raw, pack)
    relevance = infer_relevance(raw, classified.primary_area.value, pack,
                                [a.value for a in classified.secondary_areas])
    return classified, relevance


def classification_audit(sample: int = 12) -> dict[str, Any]:
    """Solo lectura: compara lo guardado con lo que las reglas vigentes clasificarían hoy."""
    pack = active_pack()
    rows = _stored()
    stored = Counter(r[5] or "sin área" for r in rows)
    drift: list[dict[str, Any]] = []
    transitions: Counter = Counter()
    for row in rows:
        classified, relevance = _reclassified(row, pack)
        new_area = classified.primary_area.value
        if (row[5] or "sin área") != new_area or row[6] != relevance.tier:
            transitions[f"{row[5] or 'sin área'} → {new_area}"] += 1
            drift.append({"job_id": row[0], "title": row[1], "stored_area": row[5], "stored_tier": row[6],
                          "current_area": new_area, "current_tier": relevance.tier, "why": classified.primary_area.evidence[:120]})
    return {
        "jobs": len(rows), "drifted": len(drift),
        "drift_pct": round(len(drift) / len(rows) * 100, 1) if rows else 0,
        "stored_by_area": stored.most_common(), "top_transitions": transitions.most_common(8),
        "sample": drift[: min(max(sample, 1), 25)],
        "hint": "Si el desfase es alto, propón reclassify_jobs (pide confirmación y guarda una copia reversible).",
    }


def reclassify_jobs() -> dict[str, Any]:
    """Reaplica las reglas vigentes a todas las ofertas guardadas (áreas y relevancia). Guarda una copia
    de lo anterior en un JSON junto a la base de datos."""
    pack = active_pack()
    rows = _stored()
    backup, changed = [], 0
    with connection() as conn:
        for row in rows:
            classified, relevance = _reclassified(row, pack)
            if (row[5] or "sin área") == classified.primary_area.value and row[6] == relevance.tier:
                continue
            backup.append({"job_id": row[0], "area": row[5], "tier": row[6]})
            _write_areas(conn, row[0], classified)
            conn.execute("UPDATE jobs SET relevance_tier=%s, relevance_score=%s, relevance_evidence=%s WHERE id=%s",
                         (relevance.tier, relevance.score, relevance.evidence, row[0]))
            changed += 1
        conn.commit()
        profile = conn.execute("SELECT id FROM user_profile ORDER BY updated_at DESC LIMIT 1").fetchone()
    path = database_path().parent / f"reclassify-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(backup, ensure_ascii=False), encoding="utf-8")
    set_setting(RULES_KEY, rules_fingerprint(pack))
    if profile:
        recompute_scores(str(profile[0]))
    return {"reclassified": changed, "unchanged": len(rows) - changed, "backup": str(path)}
