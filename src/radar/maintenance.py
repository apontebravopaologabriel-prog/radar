"""Mantenimiento de la clasificación: auditar si las áreas guardadas coinciden con las reglas vigentes
y, con confirmación, reclasificar. Nunca borra ofertas; antes de escribir guarda una copia reversible."""

from __future__ import annotations

from collections import Counter
from typing import Any

from radar.careers import active_pack, list_packs
from radar.classify import classify
from radar.db.database import connection
from radar.db.repository import _write_areas, recompute_scores
from radar.domain.models import RawJob
from radar.settings import get_setting, set_setting
from radar.taxonomy import infer_relevance

RULES_KEY = "classification_rules_hash"


def rules_fingerprint(pack=None) -> str:
    """Huella de las reglas que deciden áreas y relevancia; cambia cuando se editan."""
    from radar.markets import pack_hash

    return pack_hash(pack or active_pack())


def rules_stale() -> bool:
    """True si las reglas cambiaron desde la última reclasificación (o nunca se registró)."""
    return get_setting(RULES_KEY) != rules_fingerprint()


def _stored(market_id: str | None = None) -> list[tuple]:
    with connection() as conn:
        if market_id:
            return conn.execute(
                """SELECT j.id,j.title,j.description_raw,j.location,c.name,json_extract(m.areas,'$[0].name'),
                m.relevance_tier,m.relevance_score,m.relevance_evidence,j.content_hash
                FROM jobs j LEFT JOIN companies c ON c.id=j.company_id
                LEFT JOIN job_market_classifications m ON m.job_id=j.id AND m.market_id=%s""", (market_id,)
            ).fetchall()
        return conn.execute(
            """SELECT j.id, j.title, j.description_raw, j.location, co.name, ia.name, j.relevance_tier,
            j.relevance_score, j.relevance_evidence, j.content_hash
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


def classification_audit(sample: int = 12, market_id: str | None = None) -> dict[str, Any]:
    """Solo lectura: compara lo guardado con lo que las reglas vigentes clasificarían hoy."""
    from radar.careers import load_pack

    pack = load_pack(market_id) if market_id else active_pack()
    rows = _stored(market_id)
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
        "scope": "all_saved_offers", "market_id": pack.id,
        "jobs": len(rows), "drifted": len(drift),
        "drift_pct": round(len(drift) / len(rows) * 100, 1) if rows else 0,
        "stored_by_area": stored.most_common(), "top_transitions": transitions.most_common(8),
        "sample": drift[: min(max(sample, 1), 25)],
        "hint": "Si el desfase es alto, propón reclassify_jobs (pide confirmación y guarda una copia reversible).",
    }


def reclassify_jobs() -> dict[str, Any]:
    """Back up first, then rebuild canonical and independent market classifications."""
    from radar.markets import backfill_market
    from radar.system import backup_database

    backup = backup_database()
    pack = active_pack()
    rows = _stored()
    changed = skipped = 0
    for offset in range(0, len(rows), 50):
        # Parsing must not hold a read snapshot or a write lock during computation.
        prepared = [(row, *_reclassified(row, pack)) for row in rows[offset:offset + 50]]
        with connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for row, classified, relevance in prepared:
                updated = conn.execute(
                    """UPDATE jobs SET relevance_tier=%s,relevance_score=%s,relevance_evidence=%s
                    WHERE id=%s AND content_hash IS %s""",
                    (relevance.tier, relevance.score, relevance.evidence, row[0], row[9]),
                ).rowcount
                if not updated:
                    skipped += 1
                    continue
                _write_areas(conn, row[0], classified)
                conn.execute("DELETE FROM job_skills WHERE job_id=%s", (row[0],))
                for skill, evidence in classified.skills:
                    conn.execute(
                        """INSERT INTO job_skills(job_id,skill_id,requirement_type,importance,confidence,evidence)
                        SELECT %s,id,%s,0.7,%s,%s FROM skills WHERE name=%s""",
                        (row[0], evidence.requirement_type, evidence.confidence, evidence.evidence, skill),
                    )
                changed += int((row[5], row[6], row[7], row[8]) != (
                    classified.primary_area.value, relevance.tier, relevance.score, relevance.evidence))
    projections = {p.id: backfill_market(p.id) for p in list_packs()}
    with connection() as conn:
        profile = conn.execute("SELECT id FROM user_profile ORDER BY updated_at DESC LIMIT 1").fetchone()
    set_setting(RULES_KEY, rules_fingerprint(pack))
    if profile:
        recompute_scores(str(profile[0]))
    return {"reclassified": changed, "unchanged": len(rows) - changed - skipped,
            "skipped_changed_content": skipped, "market_projections": projections, "backup": backup["backup"]}
