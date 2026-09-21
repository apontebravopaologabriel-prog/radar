"""CV descargable por oferta: selección determinista sobre tu CV real, DOCX/PDF y chequeos.

Nada se inventa ni se reformula: solo se **eligen y ordenan** hechos de ``cv_master.json`` según su relación con
las skills de la oferta, dentro de un presupuesto de página. Cada línea conserva un ``id`` derivado de su
contenido (rastreable sin migrar el archivo). Las skills en ``falta`` nunca entran. El resultado se escribe
junto a un ``manifest.json`` que permite auditar y regenerar. Ver ``docs/cv-word-plan.md``.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from radar import cv_baseline, cv_docx, cv_targets
from radar.normalize import normalize_text

TEMPLATE = "ats-clasico-v1"
FORMATS = ("docx", "pdf")
CAPS = {1: {"bullets": 3, "projects": 2, "certs": 4}, 2: {"bullets": 5, "projects": 4, "certs": 8}}
MIN_CERTS = 2
PDF_TIMEOUT = 90
_ES_WORDS = {"de", "la", "el", "en", "y", "con", "para", "los", "las", "un", "una", "del", "experiencia", "buscamos"}
_EN_WORDS = {"the", "and", "with", "for", "of", "to", "in", "a", "we", "you", "experience", "looking", "our"}
_LABELS = {
    "es": {"summary": "Perfil", "experience": "Experiencia", "projects": "Proyectos", "education": "Formación",
           "certifications": "Certificaciones", "skills": "Habilidades", "languages": "Idiomas", "present": "Actual"},
    "en": {"summary": "Summary", "experience": "Experience", "projects": "Projects", "education": "Education",
           "certifications": "Certifications", "skills": "Skills", "languages": "Languages", "present": "Present"},
}
_MONTHS = {
    "es": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}
_OPEN_END = {"actual", "presente", "present", "en curso"}


def detect_language(text: str) -> str:
    """``es`` o ``en`` según qué palabras funcionales predominan en la oferta (por defecto ``es``)."""
    words = re.findall(r"[a-záéíóúñ]+", text.lower())
    spanish, english = sum(w in _ES_WORDS for w in words), sum(w in _EN_WORDS for w in words)
    return "en" if english > spanish * 1.3 and english >= 8 else "es"


def _item_id(kind: str, owner: str, text: str) -> str:
    digest = hashlib.sha1(f"{normalize_text(owner)}|{normalize_text(text)}".encode()).hexdigest()
    return f"{kind}:{digest[:8]}"


def _date(value: str | None, lang: str) -> str:
    if not value:
        return ""
    if normalize_text(value) in _OPEN_END:
        return _LABELS[lang]["present"]
    match = re.match(r"^(\d{4})-(\d{2})$", value)
    if match and 1 <= int(match.group(2)) <= 12:
        return f"{_MONTHS[lang][int(match.group(2)) - 1]} {match.group(1)}"
    return value


def _span(start: str | None, end: str | None, lang: str) -> str:
    left, right = _date(start, lang), _date(end, lang)
    return f"{left} – {right}" if left and right else left or right


def _recency(value: str | None) -> int:
    """Orden ascendente para fechas AAAA-MM o AAAA: las más recientes primero; sin fecha, al final."""
    match = re.match(r"^(\d{4})(?:-(\d{2}))?", value or "")
    return -(int(match.group(1)) * 100 + int(match.group(2) or 0)) if match else 0


def _score(text: str, wanted: list[dict[str, Any]]) -> tuple[float, list[str]]:
    matched = [w for w in wanted if any(cv_baseline._contains(text, term) for term in w["terms"])]
    return sum(w["weight"] for w in matched), [w["label"] for w in matched]


def _pages_budget(profile: dict[str, Any], job: dict[str, Any]) -> int:
    months = sum(cv_baseline._months(j.get("from"), j.get("to")) for j in profile.get("experience", []))
    junior = re.search(r"\b(practicante|trainee|junior|intern|internship|pr[aá]cticas)\b",
                       normalize_text(f"{job['title']} {job.get('description') or ''}"))
    return 1 if months < 36 or junior else 2


def _wanted(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    wanted = []
    for item in items:
        if item["category"] != "skill":
            continue
        weight = cv_baseline._WEIGHT.get(item.get("requirement", "unknown"), 0.8)
        wanted.append({"label": item["label"], "key": item["key"], "status": item["status"], "weight": weight,
                       "terms": cv_baseline._terms(item["label"])})
    return wanted


def select(job_id: str, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Qué entra y qué se omite (con motivo) en el CV para esta oferta. No escribe archivos."""
    profile = profile if profile is not None else cv_targets.load_profile()
    if not profile:
        raise ValueError("No hay CV cargado (cv_master.json): créalo antes de generar un CV.")
    job = cv_targets._job_context(job_id)
    if job is None:
        raise ValueError(f"Oferta no encontrada: {job_id}")
    items = cv_baseline.baseline(job_id, profile)
    wanted = _wanted(items)
    lang = detect_language(f"{job['title']} {job.get('description') or ''}")
    pages = _pages_budget(profile, job)
    caps = CAPS[pages]
    omitted: list[dict[str, Any]] = []

    def leave_out(kind: str, section: str, text: str, reason: str) -> None:
        omitted.append({"id": _item_id(kind, section, text), "section": section, "text": text, "reason": reason})

    experience = []
    roles = sorted(profile.get("experience", []), key=lambda j: j.get("from") or "", reverse=True)
    for role in roles:
        owner = f"{role.get('role')}|{role.get('company')}"
        ranked = sorted(enumerate(role.get("bullets", [])),
                        key=lambda pair: (-_score(pair[1], wanted)[0], pair[0]))
        kept = []
        for position, (_, bullet) in enumerate(ranked):
            score, matched = _score(bullet, wanted)
            if position < caps["bullets"]:
                kept.append({"id": _item_id("exp", owner, bullet), "text": bullet, "score": score, "matched": matched})
            else:
                leave_out("exp", "experience", bullet,
                          "Menos relacionada con la oferta que las elegidas" if score else "No menciona skills de la oferta")
        experience.append({
            "id": _item_id("role", owner, ""), "title": f"{role.get('role')} — {role.get('company')}",
            "detail": " · ".join(x for x in (role.get("location"), _span(role.get("from"), role.get("to"), lang)) if x),
            "text": " ".join([role.get("role") or "", role.get("company") or "", *role.get("bullets", []), *role.get("skills", [])]),
            "bullets": kept,
        })

    projects = []
    scored = sorted(((_score(" ".join([p.get("name") or "", p.get("description") or "", *p.get("skills", [])]), wanted), p)
                     for p in profile.get("projects", [])), key=lambda pair: -pair[0][0])
    for (score, matched), project in scored:
        text = project.get("name") or ""
        if score > 0 and len(projects) < caps["projects"]:
            projects.append({"id": _item_id("proj", "proyecto", text), "title": text, "detail": _date(project.get("date"), lang),
                             "bullets": [{"id": _item_id("projd", text, project.get("description") or ""),
                                          "text": project.get("description") or "", "score": score, "matched": matched}]
                             if project.get("description") else [], "matched": matched, "score": score})
        else:
            leave_out("proj", "projects", text, "No se relaciona con la oferta" if score == 0 else "Fuera del presupuesto de página")

    ranked_certs = sorted(profile.get("certifications", []),
                          key=lambda c: (-_score(c.get("name") or "", wanted)[0], _recency(c.get("date"))))
    certs = []
    for cert in ranked_certs:
        score, matched = _score(cert.get("name") or "", wanted)
        if len(certs) < caps["certs"] and (score > 0 or len(certs) < MIN_CERTS):
            certs.append({"id": _item_id("cert", "certificado", cert.get("name") or ""), "title": cert.get("name") or "",
                          "detail": " · ".join(x for x in (cert.get("issuer"), _date(cert.get("date"), lang)) if x),
                          "score": score, "matched": matched})
        else:
            leave_out("cert", "certifications", cert.get("name") or "", "No se relaciona con la oferta")

    education = [{"id": _item_id("edu", "formacion", f"{s.get('program')}|{s.get('institution')}"),
                  "title": f"{s.get('program')} — {s.get('institution')}",
                  "detail": " · ".join(x for x in (_span(s.get("from"), s.get("to"), lang), s.get("status")) if x)}
                 for s in sorted(profile.get("education", []), key=lambda s: s.get("to") or "", reverse=True)]

    # Solo skills con evidencia (cubierto o parcial); las que faltan no se listan aunque la oferta las pida.
    skills = [w["label"] for w in sorted((w for w in wanted if w["status"] != "falta"),
                                         key=lambda w: (w["status"] != "cubierto", -w["weight"], w["label"]))]
    languages = [f"{lang_.get('name')}" + (f" ({lang_.get('level')})" if lang_.get("level") else "") for lang_ in profile.get("languages", [])]
    contact = profile.get("contact") or {}
    header = {
        "name": profile.get("name") or "",
        "headline": profile.get("headline") or "",
        "contact": " · ".join(x for x in (contact.get("email"), contact.get("phone"), contact.get("linkedin"),
                                          contact.get("location") or profile.get("home_district")) if x),
    }
    selection = {
        "job": {"id": job_id, "title": job["title"], "company": job["company"]}, "language": lang, "pages_budget": pages,
        "template": TEMPLATE, "header": header, "summary": profile.get("summary") or "",
        "experience": experience, "projects": projects, "certifications": certs, "education": education,
        "skills": skills, "languages": languages, "omitted": omitted,
    }
    selection["coverage"] = coverage(selection, wanted)
    selection["warnings"] = _warnings(selection, bool(contact.get("email") or contact.get("phone")))
    return selection


_PLACEHOLDER = re.compile(r"\([^)]*(?:no indicad|no declarad|en pdf|por definir|pendiente)[^)]*\)", re.IGNORECASE)


def _warnings(selection: dict[str, Any], has_contact: bool) -> list[str]:
    """Avisos antes de enviar: contacto ausente y marcadores de dato pendiente en tu CV real."""
    warnings = [] if has_contact else [
        "Tu CV no tiene datos de contacto: pídele al agente que los añada (update_cv, sección contact)."]
    seen: list[str] = []
    for block in to_blocks(selection):
        for text in block[1:]:
            for found in _PLACEHOLDER.finditer(text or ""):
                if found.group(0) not in seen:
                    seen.append(found.group(0))
    if seen:
        warnings.append("Tu CV real contiene marcadores de dato pendiente que saldrían en el documento: "
                        + ", ".join(seen) + ". Corrígelos antes de enviarlo (update_cv).")
    return warnings


def _body_text(selection: dict[str, Any]) -> str:
    parts = [selection["summary"]]
    for role in selection["experience"]:
        parts += [role["title"], *(b["text"] for b in role["bullets"])]
    for project in selection["projects"]:
        parts += [project["title"], *(b["text"] for b in project["bullets"])]
    parts += [c["title"] for c in selection["certifications"]]
    return "\n".join(parts)


def coverage(selection: dict[str, Any], wanted: list[dict[str, Any]]) -> dict[str, Any]:
    """Skills de la oferta según su respaldo en el CV generado: demostradas, solo listadas o ausentes."""
    body = _body_text(selection)
    shown, listed, absent = [], [], []
    for skill in wanted:
        if any(cv_baseline._contains(body, term) for term in skill["terms"]):
            shown.append(skill["label"])
        elif skill["status"] != "falta":
            listed.append(skill["label"])
        else:
            absent.append(skill["label"])
    total = len(wanted)
    return {
        "demonstrated": shown, "listed_only": listed, "missing": absent,
        "percent": round(100 * (len(shown) + len(listed)) / total) if total else None,
        "note": "«Ausentes» no está en tu perfil: no se añaden al CV; véalas en el Plan de cierre. «Solo listadas» "
                "están en tu perfil pero sin respaldo en experiencia o proyectos: conviene documentarlas.",
    }


def to_blocks(selection: dict[str, Any]) -> list[cv_docx.Block]:
    labels = _LABELS[selection["language"]]
    header = selection["header"]
    blocks: list[cv_docx.Block] = [("name", header["name"]), ("headline", header["headline"]), ("contact", header["contact"])]
    if selection["summary"]:
        blocks += [("heading", labels["summary"]), ("para", selection["summary"])]
    if selection["experience"]:
        blocks.append(("heading", labels["experience"]))
        for role in selection["experience"]:
            blocks.append(("entry", role["title"], role["detail"]))
            blocks += [("bullet", b["text"]) for b in role["bullets"]]
    if selection["projects"]:
        blocks.append(("heading", labels["projects"]))
        for project in selection["projects"]:
            blocks.append(("entry", project["title"], project["detail"]))
            blocks += [("bullet", b["text"]) for b in project["bullets"]]
    if selection["education"]:
        blocks.append(("heading", labels["education"]))
        blocks += [("entry", e["title"], e["detail"]) for e in selection["education"]]
    if selection["certifications"]:
        blocks.append(("heading", labels["certifications"]))
        blocks += [("entry", c["title"], c["detail"]) for c in selection["certifications"]]
    if selection["skills"]:
        blocks += [("heading", labels["skills"]), ("para", ", ".join(selection["skills"]))]
    if selection["languages"]:
        blocks += [("heading", labels["languages"]), ("para", ", ".join(selection["languages"]))]
    return blocks


def _slug(value: str, limit: int = 40) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", normalize_text(value)).strip("_")
    return text[:limit].strip("_") or "CV"


def cvs_dir() -> Path:
    return cv_targets.data_dir() / "cvs"


def _unique(directory: Path, stem: str) -> str:
    """Nombre que no existe aún: nunca se sobrescribe un CV ya generado."""
    name, count = stem, 1
    while any(directory.glob(f"{name}.*")):
        count += 1
        name = f"{stem}-{count}"
    return name


def _to_pdf(docx: Path) -> tuple[Path | None, str | None]:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice is None:
        return None, "LibreOffice no está instalado: solo se generó el DOCX."
    with tempfile.TemporaryDirectory() as profile_dir:
        try:
            subprocess.run(
                [soffice, f"-env:UserInstallation=file://{profile_dir}", "--headless", "--convert-to", "pdf",
                 "--outdir", str(docx.parent), str(docx)],
                check=True, capture_output=True, timeout=PDF_TIMEOUT)
        except (subprocess.SubprocessError, OSError) as exc:
            return None, f"No se pudo convertir a PDF ({type(exc).__name__}); el DOCX sí se generó."
    pdf = docx.with_suffix(".pdf")
    return (pdf, None) if pdf.exists() else (None, "La conversión a PDF no produjo archivo.")


def check_pdf(pdf: Path, budget: int) -> dict[str, Any]:
    """Páginas y texto extraíble del PDF (necesita ``pdfinfo``/``pdftotext``; si faltan, se informa)."""
    result: dict[str, Any] = {"pages": None, "text_extractable": None, "within_budget": None}
    if shutil.which("pdfinfo"):
        info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=20, check=False)
        match = re.search(r"^Pages:\s+(\d+)", info.stdout, re.MULTILINE)
        if match:
            result["pages"] = int(match.group(1))
            result["within_budget"] = result["pages"] <= budget
    if shutil.which("pdftotext"):
        text = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True, timeout=20, check=False).stdout
        result["text_extractable"] = len(text.strip()) > 100
    return result


def build(job_id: str, formats: list[str] | None = None) -> dict[str, Any]:
    """Genera los archivos del CV para una oferta en ``cvs/<fecha>/`` y devuelve rutas, chequeos y selección."""
    wanted_formats = [f for f in (formats or list(FORMATS)) if f in FORMATS]
    if not wanted_formats:
        raise ValueError(f"formats debe incluir alguno de: {', '.join(FORMATS)}")
    selection = select(job_id)
    stamp = datetime.now(UTC)
    directory = cvs_dir() / stamp.strftime("%Y-%m-%d")
    stem = _unique(directory, f"CV_{_slug(selection['job']['company'] or 'Empresa')}_{_slug(selection['job']['title'])}")
    docx = cv_docx.write_docx(directory / f"{stem}.docx", to_blocks(selection),
                              title=f"CV {selection['header']['name']}", author=selection["header"]["name"],
                              lang="en-US" if selection["language"] == "en" else "es-PE")
    files = [{"format": "docx", "name": docx.name, "path": f"{docx.parent.name}/{docx.name}"}]
    notes: list[str] = []
    check: dict[str, Any] = {}
    if "pdf" in wanted_formats:
        pdf, problem = _to_pdf(docx)
        if pdf:
            files.append({"format": "pdf", "name": pdf.name, "path": f"{pdf.parent.name}/{pdf.name}"})
            check = check_pdf(pdf, selection["pages_budget"])
            if check.get("within_budget") is False:
                notes.append(f"El PDF tiene {check['pages']} páginas y el presupuesto era {selection['pages_budget']}.")
        if problem:
            notes.append(problem)
    profile_file = cv_targets.data_dir() / "cv_master.json"
    manifest = {
        "created_at": stamp.isoformat(timespec="seconds"), "job": selection["job"], "template": TEMPLATE,
        "language": selection["language"], "pages_budget": selection["pages_budget"],
        "profile_sha256": hashlib.sha256(profile_file.read_bytes()).hexdigest() if profile_file.exists() else None,
        "included_ids": [role["id"] for role in selection["experience"]]
        + [b["id"] for role in selection["experience"] for b in role["bullets"]]
        + [p["id"] for p in selection["projects"]] + [c["id"] for c in selection["certifications"]],
        "omitted": selection["omitted"], "coverage": selection["coverage"], "files": [f["name"] for f in files],
    }
    (directory / f"{stem}.manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"files": files, "check": check, "notes": notes, "selection": selection}


def resolve_file(relative: str) -> Path | None:
    """Ruta absoluta de un CV generado, solo dentro de ``cvs/`` y solo .docx/.pdf; ``None`` si no procede."""
    root = cvs_dir().resolve()
    try:
        path = (root / relative).resolve()
    except (OSError, ValueError):
        return None
    if root not in path.parents or path.suffix.lower() not in {".docx", ".pdf"} or not path.is_file():
        return None
    return path
