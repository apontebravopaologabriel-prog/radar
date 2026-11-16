"""Herramientas de CV real y dossier de entrevista."""

from __future__ import annotations

from radar.cv import baseline as cv_baseline
from radar.cv import edit as cv_edit
from radar.cv import store as cv_store
from radar.tools.registry import tool


@tool()
def get_my_cv() -> dict:
    """Tu CV real (cv_master) y preferencias de perfil en 1 llamada: resumen, experiencia, formación,
    certificaciones, idiomas, proyectos, áreas objetivo, modalidades y herramientas declaradas con nivel.
    Úsala cuando pregunten por tu trayectoria, skills o cómo te ves frente a un puesto."""
    from radar.db.queries import get_profile

    cv = cv_store.load_profile()
    profile = get_profile()
    if cv is None:
        return {
            "cv": None,
            "profile": profile,
            "note": "Aún no hay CV cargado. Abre Mi CV para importar un PDF/Word o completar tus datos.",
        }
    return {
        "cv": {k: v for k, v in cv.items() if not k.startswith("_") and k != "has_photo"},
        "profile": profile,
    }


@tool(write=True)
def update_cv(section: str, action: str, item: dict | None = None, match: str | None = None) -> dict:
    """Edita tu CV real (Mi CV). section: certifications {name, issuer, date AAAA-MM}, experience {role,
    company, location, from, to, bullets[]}, education {institution, program, from, to, status, skills[]}, languages
    {name, level, evidence}, projects {name, description, skills[], date, link}, contact {email, phone, linkedin,
    location} (action update), gaps {text}, summary o headline {text}. action: add | update | remove; en update y remove,
    `match` es un texto que identifica el ítem. Solo con lo que la persona dictó: pregunta lo que falte (emisor,
    fecha). Guarda copia previa. Skills y herramientas: update_profile."""
    return cv_edit.update_cv(section, action, item, match)


@tool(chat=False)
def resolve_nearest_districts(reference: str, limit: int = 3) -> dict:
    """Distritos más cercanos a una zona mencionada en una oferta, con km aproximados."""
    return {"districts": cv_store.districts_near(reference, limit)}


@tool(chat=False)
def get_interview_dossier(query_or_job_id: str) -> dict:
    """Dossier completo en 1 sola llamada para preparar entrevistas o narrativa en Markdown: busca la oferta por ID o
    texto (incluyendo automáticamente ofertas ya postuladas `applied`, en entrevista o históricas de hasta 365 días) y
    devuelve la descripción completa guardada, tu seguimiento (`your_tracking`), el puntaje y desglose de encaje (`fit`),
    la brecha determinista (`baseline` y `readiness`), la selección de balas relevantes de tu CV (`cv_selection`) y tu
    `cv_master` real completo."""
    from radar import insights
    from radar.db.database import connection

    needle = (query_or_job_id or "").strip()
    if not needle:
        raise ValueError("Indica el ID de la oferta o el nombre de la empresa/puesto")

    details = None
    other_matches: list[dict] = []
    try:
        details = insights.job_details(needle)
    except ValueError:
        like = f"%{needle}%"
        with connection() as conn:
            rows = conn.execute(
                """SELECT j.id, j.title, c.name, j.location, j.published_at, j.relevance_score,
                          a.status AS user_application, a.notes AS app_notes,
                          EXISTS(SELECT 1 FROM job_user_favorites f WHERE f.job_id=j.id) AS is_favorite
                   FROM jobs j
                   LEFT JOIN companies c ON c.id=j.company_id
                   LEFT JOIN applications a ON a.job_id=j.id
                   WHERE j.duplicate_status='canonical'
                     AND (j.title LIKE %s OR c.name LIKE %s OR a.notes LIKE %s OR j.description_clean LIKE %s)
                   ORDER BY CASE a.status
                              WHEN 'interview' THEN 0
                              WHEN 'interviewing' THEN 0
                              WHEN 'offer' THEN 1
                              WHEN 'applied' THEN 2
                              WHEN 'saved' THEN 3
                              ELSE 4
                            END,
                            is_favorite DESC,
                            j.published_at DESC NULLS LAST
                   LIMIT 8""",
                (like, like, like, like),
            ).fetchall()
        if not rows:
            return {"found": False, "query": needle, "matches": []}
        best_id = str(rows[0][0])
        details = insights.job_details(best_id)
        other_matches = [
            {
                "id": r[0],
                "title": r[1],
                "company": r[2],
                "location": r[3],
                "published_at": str(r[4] or ""),
                "user_application": r[6],
                "notes": r[7],
                "is_favorite": bool(r[8]),
            }
            for r in rows[1:5]
        ]

    job_id = str(details["id"])
    raw_cv = cv_store.load_profile() or {}
    clean_cv = {k: v for k, v in raw_cv.items() if not k.startswith("_") and k != "has_photo"} if raw_cv else None
    base = cv_baseline.baseline(job_id, raw_cv) if raw_cv else None
    readiness = cv_baseline.readiness(base, details.get("description") or "") if base else None

    return {
        "found": True,
        "job": details,
        "baseline": base,
        "readiness": readiness,
        "real_cv": clean_cv,
        "other_matches": other_matches,
    }
