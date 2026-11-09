"""Herramientas de CV real, CVs objetivo hipotéticos, Estudio de CV y paquetes de postulación."""

from __future__ import annotations

from radar import (
    cv_baseline,
    cv_doc,
    cv_edit,
    cv_packages,
    cv_plan,
    cv_targets,
)
from radar.tools_registry import tool


@tool()
def get_my_cv() -> dict:
    """Tu CV real (cv_master): resumen, experiencia, formación, certificaciones, idiomas, herramientas declaradas y
    brechas de evidencia. Úsala cuando pregunten por tu experiencia, formación, certificaciones o cómo te ves
    frente a un puesto. Es la fuente sobre tu trayectoria; get_user_profile solo trae skills y preferencias."""
    cv = cv_targets.load_profile()
    if cv is None:
        return {"cv": None, "note": "Aún no hay CV cargado. Abre Mi CV para importar un PDF/Word o completar tus datos."}
    return {"cv": {k: v for k, v in cv.items() if not k.startswith("_") and k != "has_photo"}}


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
def get_target_context(job_ids: list[str]) -> dict:
    """Contexto para redactar CVs objetivo hipotéticos: ofertas (requisitos, skills, descripción,
    distancia desde el distrito real) y el perfil real. Máximo 10 ofertas."""
    context = cv_targets.get_target_context(job_ids)
    profile = context.get("real_profile") or {}
    for job in context["jobs"]:
        if "error" not in job:
            base = cv_baseline.baseline(job["job_id"], profile)
            job["baseline"] = base
            job["readiness"] = cv_baseline.readiness(base, job.get("description") or "")
    return context


@tool(chat=False)
def list_targets() -> dict:
    """Objetivos actuales (ofertas con estrella) ordenados por cercanía al perfil real, con su brecha
    base calculada por código. La selección la hace el usuario desde la interfaz."""
    return {"targets": cv_baseline.ranked_selection()}


@tool(write=True, chat=False)
def save_target_profile(job_id: str, profile: dict) -> dict:
    """Guarda un CV objetivo HIPOTÉTICO (nunca el CV real ni enviable). `profile` lleva `sections`
    (summary, experience, tools, education, certifications) con ítems {text, origin, quote?, reason?,
    key?, label?, status?} y `gaps` [{item, kind, action, estimate_days?, evidence_to_produce?}].
    origin: explicito (cita), inferido (con reason) o tipico. status: cubierto (con reason citando el
    perfil real), parcial o falta. kind: dias, semanas o no_cerrable_rapido. `key` agrupa el mismo requisito entre puestos en la matriz y `label` es su nombre corto. Devuelve errores si el
    esquema no valida; el estado de los requisitos que Radar ya calculó (`baseline`, con su `key`) no
    se puede reasignar: prevalece el del código; la empresa, el título y la distancia los calcula Radar."""
    return cv_targets.save_target(job_id, profile)


@tool()
def get_closure_plan(limit: int = 10) -> dict:
    """Plan para cerrar brechas entre tus objetivos (ofertas con estrella): qué skills cerrar primero, cuántos
    puntos de cercanía sube cada una en cada puesto, en cuántos objetivos aparece y qué % del mercado reciente
    la pide. Incluye lo estructural (años de experiencia, grado), que un curso no cierra, y lo cerrado
    recientemente. Úsala cuando pregunten qué aprender o demostrar primero."""
    return cv_plan.closure_plan(limit)


@tool()
def preview_cv(job_id: str) -> dict:
    """Vista previa del CV descargable para una oferta, sin escribir archivos: qué se incluye de tu CV real, qué
    se omite y por qué, el idioma detectado, el presupuesto de páginas y la cobertura de skills de la oferta
    (demostradas en el cuerpo, solo listadas, ausentes). Nada se inventa: solo elige y ordena lo que ya tienes."""
    return cv_doc.state(job_id)["selection"]


@tool(write=True)
def build_cv(job_id: str, formats: list[str] | None = None) -> dict:
    """Descarga el CV vigente para una oferta (formats: pdf, docx) a su carpeta de postulación.
    Respeta los cambios revisados en Mi CV. Alias de prepare_application; nunca envía nada."""
    return cv_packages.export(job_id, formats)


def _clip(text: str, limit: int = 160) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


@tool()
def cv_doc_get(job_id: str) -> dict:
    """Estado del CV de una oferta en el Estudio, tal como lo ve la persona: líneas incluidas (con `id`, texto y de qué cargo
    salen), líneas omitidas y por qué, plantilla, foto, páginas frente al presupuesto, cobertura de skills, avisos y
    sugerencias pendientes. Úsala SIEMPRE antes de proponer cambios: los `id` son los de este resultado."""
    state = cv_doc.state(job_id)
    selection = state["selection"]
    lines: list[dict] = [{"id": "summary", "kind": "perfil", "text": _clip(selection["summary"])},
                         {"id": "headline", "kind": "titular", "text": selection["header"]["headline"]}]
    for role in selection["experience"]:
        lines.append({"id": role["id"], "kind": "cargo", "text": role["title"]})
        lines += [{"id": b["id"], "kind": "viñeta", "text": _clip(b["text"]), "edited": b.get("edited")} for b in role["bullets"]]
    for project in selection["projects"]:
        lines.append({"id": project["id"], "kind": "proyecto", "text": project["title"]})
        lines += [{"id": b["id"], "kind": "viñeta de proyecto", "text": _clip(b["text"])} for b in project["bullets"]]
    lines += [{"id": c["id"], "kind": "certificado", "text": c["title"]} for c in selection["certifications"]]
    lines += [{"id": e["id"], "kind": "formación", "text": e["title"]} for e in selection["education"]]
    return {
        "job": selection["job"], "language": selection["language"], "template": state["document"]["template"],
        "photo": state["document"]["photo"], "pages": state["render"]["pages"], "pages_budget": state["document"]["pages_budget"],
        "over_budget": state["render"]["over_budget"], "lines": lines,
        "omitted": [{"id": o["id"], "text": _clip(o["text"], 100), "reason": o["reason"]} for o in selection["omitted"]],
        "coverage": selection["coverage"], "warnings": state["warnings"], "pending_suggestions": len(state["suggestions"]),
        "templates": state["templates"],
    }


@tool()
def cv_doc_propose(job_id: str, ops: list[dict], note: str = "") -> dict:
    """Propone cambios al CV de una oferta; NO cambian nada hasta que la persona los acepte en el Estudio (antes/después).
    `ops`: lista de operaciones sobre ids de `cv_doc_get`: {"op":"omit","id"}, {"op":"include","id"} (de las omitidas),
    {"op":"move","id","to":índice}, {"op":"edit","id","text"} (reformular una línea) y {"op":"option","name":"template"|"photo"|"pages",
    "value"}. REGLAS: al reformular usa SOLO hechos que ya están en esa línea o en su cargo: un número, empresa, herramienta o
    logro nuevo se marca en rojo y no se puede aceptar. No inventes. Para añadir un dato verdadero, la persona lo agrega a su CV
    maestro (update_cv). `note` explica el porqué en una frase."""
    return cv_doc.propose(job_id, ops, note)


@tool(write=True)
def prepare_application(job_id: str, formats: list[str] | None = None) -> dict:
    """Prepara la postulación: exporta el CV vigente del Estudio (formats: pdf, docx) a la carpeta de esa oferta, junto con una
    copia de la oferta y el registro de lo que se generó. NO envía nada ni postula: la persona sube el archivo en el portal y
    luego lo marca como enviado. Avisa si el CV excede las páginas o tiene advertencias."""
    return cv_packages.export(job_id, formats)


@tool()
def list_application_packages(limit: int = 20) -> dict:
    """Postulaciones preparadas: oferta, carpeta, archivos, estado (preparada o enviada) y fechas. Responde «¿qué CV mandé a
    tal empresa?» y «¿qué tengo preparado?»."""
    return {"packages": [{"job_id": p["job_id"], "title": p["title"], "company": p["company"], "status": p["status"],
                          "exported_at": p["exported_at"], "applied_at": p["applied_at"], "folder": p["folder"],
                          "files": [f["name"] for f in p["files"]]} for p in cv_packages.list_packages(limit)]}


@tool(write=True)
def close_gap(skill: str, kind: str, name: str, issuer: str | None = None, date: str | None = None,
              description: str | None = None, link: str | None = None) -> dict:
    """Registra evidencia REAL que cierra una brecha (la persona la aportó; no inventes nada). skill: la brecha
    (ej. «SQL»). kind: certificado (name debe mencionar la skill; issuer, date AAAA-MM) o proyecto (name y
    description de lo que hizo, mín. 15 caracteres; link opcional). Lo guarda en el CV, quita la nota de brecha
    equivalente, lo anota en la línea de tiempo y devuelve la cercanía de cada objetivo antes y después."""
    return cv_plan.close_gap(skill, kind, name, issuer, date, description, link)


@tool(chat=False)
def get_target_matrix() -> dict:
    """Matriz de brechas entre los CVs objetivo guardados (requisitos con `key` por puesto)."""
    return cv_targets.build_matrix(cv_targets.load_targets())


@tool(chat=False)
def resolve_nearest_districts(reference: str, limit: int = 3) -> dict:
    """Distritos más cercanos a una zona mencionada en una oferta, con km aproximados."""
    return {"districts": cv_targets.districts_near(reference, limit)}


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
    raw_cv = cv_targets.load_profile() or {}
    clean_cv = {k: v for k, v in raw_cv.items() if not k.startswith("_") and k != "has_photo"} if raw_cv else None
    base = cv_baseline.baseline(job_id, raw_cv) if raw_cv else None
    readiness = cv_baseline.readiness(base, details.get("description") or "") if base else None
    selection = None
    if raw_cv:
        try:
            sel = cv_doc.state(job_id)["selection"]
            selection = {
                "language": sel.get("language"),
                "coverage": sel.get("coverage"),
                "experience": sel.get("experience"),
                "projects": sel.get("projects"),
                "omitted": sel.get("omitted"),
            }
        except Exception:  # noqa: BLE001
            selection = None

    return {
        "found": True,
        "job": details,
        "baseline": base,
        "readiness": readiness,
        "cv_selection": selection,
        "real_cv": clean_cv,
        "other_matches": other_matches,
    }
