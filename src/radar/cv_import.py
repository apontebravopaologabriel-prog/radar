"""Local, bounded CV extraction and explicit, resumable profile setup."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import zipfile
from functools import cache
from pathlib import Path
from xml.etree import ElementTree

from radar import cv_edit, cv_profile, cv_targets
from radar.careers import load_pack
from radar.db.database import connection, database_path
from radar.normalize import normalize_text
from radar.requirements import qualification_aliases
from radar.settings import get_json_setting, set_json_setting

MAX_BYTES = 8 * 1024 * 1024
MAX_TEXT = 60_000
DRAFT_KEY = "setup_draft_v1"
IMPORT_SECTIONS = tuple(cv_edit.LIST_SECTIONS)
_HEADINGS = {
    "perfil": "summary", "perfil profesional": "summary", "resumen": "summary", "sobre mi": "summary", "summary": "summary",
    "experiencia": "experience", "experiencia laboral": "experience", "experiencia profesional": "experience", "work experience": "experience",
    "educacion": "education", "formacion": "education", "formacion academica": "education", "estudios": "education", "educacion superior": "education", "education": "education",
    "certificaciones": "certifications", "certificados": "certifications", "cursos": "certifications", "cursos y certificaciones": "certifications", "certifications": "certifications",
    "proyectos": "projects", "proyectos personales": "projects", "proyectos academicos": "projects", "projects": "projects",
    "idiomas": "languages", "languages": "languages", "habilidades": "skills", "herramientas": "skills", "skills": "skills",
}


def _section_lines(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = "header"
    for line in lines:
        heading = _HEADINGS.get(normalize_text(line).strip(": "))
        if heading:
            current = heading
        else:
            sections.setdefault(current, []).append(line)
    return sections


def extract_text(data: bytes, filename: str) -> str:
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Adjunta un CV de hasta 8 MB.")
    suffix = Path(filename).suffix.lower()
    try:
        if suffix == ".pdf" and data.startswith(b"%PDF-"):
            import pypdfium2 as pdfium

            with pdfium.PdfDocument(data) as document:
                if len(document) > 20:
                    raise ValueError("El CV admite hasta 20 páginas.")
                chunks = []
                for page in document:
                    textpage = page.get_textpage()
                    try:
                        chunks.append(textpage.get_text_bounded())
                    finally:
                        textpage.close()
                        page.close()
                    if sum(map(len, chunks)) > MAX_TEXT:
                        raise ValueError("El CV contiene demasiado texto.")
                text = "\n".join(chunks)
        elif suffix == ".docx" and data.startswith(b"PK"):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if len(archive.infolist()) > 1000 or sum(x.file_size for x in archive.infolist()) > 20*1024*1024:
                    raise ValueError("El documento Word es demasiado grande al descomprimirlo.")
                root = ElementTree.fromstring(archive.read("word/document.xml"))
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                text = "\n".join("".join(t.text or "" for t in p.findall(".//w:t", ns))
                                 for p in root.findall(".//w:p", ns))
        else:
            raise ValueError("Usa un PDF con texto o Word .docx. Convierte los archivos .doc antes de adjuntarlos.")
    except (RuntimeError, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise ValueError("No se pudo leer el CV. Revisa si está protegido o dañado.") from exc
    if len(text) > MAX_TEXT:
        raise ValueError("El CV contiene demasiado texto.")
    if len(text.strip()) < 30:
        raise ValueError("No encontramos texto legible. Si es un escaneo, conviértelo a PDF con texto o usa Word .docx.")
    return text.replace("\x00", "")


_MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
           "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
_DATE_TOKEN = re.compile(r"\b(?:(?:19|20)\d{2}-(?:0[1-9]|1[0-2])|(?:0[1-9]|1[0-2])/(?:19|20)\d{2}|(?:" + "|".join(_MONTHS) + r")\s+(?:de\s+)?(?:19|20)\d{2}|(?:19|20)\d{2}|actualidad|presente|actual)\b")


def dates_in(text):
    dates = []
    for match in _DATE_TOKEN.finditer(normalize_text(text)):
        value = match.group()
        if value in {"actualidad", "presente", "actual"}:
            value = "actual"
        elif "/" in value:
            month, year = value.split("/")
            value = f"{year}-{month}"
        elif value.split()[0] in _MONTHS:
            value = f"{value.split()[-1]}-{_MONTHS[value.split()[0]]:02d}"
        dates.append(value)
    return dates


def parse_text(text: str, career_id: str, filename="") -> dict:
    pack = load_pack(career_id)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    sections = _section_lines(lines)
    contact = {}
    email = re.search(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", text)
    phone = re.search(r"(?<!\d)(?:\+51[ -]?)?9(?:[ -]?\d){8}(?!\d)", text)
    if email:
        contact["email"] = email.group()
    if phone:
        contact["phone"] = phone.group()
    linkedin = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w%-]+/?", text, re.IGNORECASE)
    if linkedin:
        contact["linkedin"] = "https://" + re.sub(r"^https?://", "", linkedin.group(), flags=re.IGNORECASE)
    name = ""
    for line in lines[:6]:
        candidate = re.sub(r"^(?:nombre(?: completo)?\s*:)\s*", "", line, flags=re.IGNORECASE)
        if 2 <= len(candidate.split()) <= 6 and len(candidate) <= 80 and not re.search(r"[\d@:/|]", candidate) and not re.search(
            r"curriculum|vitae|ingenier|bachiller|estudiant|egresad|perfil|experiencia|profesional", normalize_text(candidate)
        ):
            name = candidate
            break
    education = []
    academic = False
    institution = ""
    for line in lines:
        norm = normalize_text(line)
        if _HEADINGS.get(norm.strip(": ")) == "education":
            academic = True
            continue
        if _HEADINGS.get(norm.strip(": ")) not in {None, "education"}:
            academic = False
            institution = ""
        if academic and re.search(r"\b(?:universidad|instituto)\b", norm):
            institution = line[:300]
        if (academic or re.search(r"^(?:estudiante|egresad[oa]|bachiller|titulad[oa])\b", norm)) and any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", norm)
               for aliases in qualification_aliases().values() for alias in aliases):
            status = re.search(r"\b(?:en curso|estudiante|egresad[oa]|bachiller|titulad[oa])\b", norm)
            education.append({"program": line[:300], "institution": institution, "status": status.group() if status else ""})
    experience = []
    section = ""
    for i, line in enumerate(lines):
        norm = normalize_text(line).strip(": ")
        if _HEADINGS.get(norm) == "experience":
            section = "experience"
            continue
        if _HEADINGS.get(norm) not in {None, "experience"}:
            section = ""
        if section != "experience":
            continue
        role_line = re.sub(r"^cargo\s*:\s*", "", line, flags=re.IGNORECASE)
        is_role = re.match(r"^(?:analista|asistente|auxiliar|ingenier[oa]|practicante|supervisor|jefe|gerente|coordinador|tecnico|desarrollador)\b", normalize_text(role_line))
        if " | " in line or " — " in line:
            parts = re.split(r" \| | — ", line, maxsplit=1)
            role, company = parts[0], parts[1]
        elif is_role:
            role, company = role_line, ""
            for nearby in (lines[i+1:i+2] + lines[max(0,i-1):i]):
                if re.search(r"^empresa\s*:|\b(?:sac|s\.a\.c|eirl|s\.a\.)\b", normalize_text(nearby)):
                    company = re.sub(r"^empresa\s*:\s*", "", nearby, flags=re.IGNORECASE)
                    break
        else:
            continue
        dates = dates_in(" ".join(lines[i:i+4]))
        entry = {"role": role[:300], "company": company[:300], "from": dates[0] if dates else "",
                 "to": dates[1] if len(dates)>1 else "", "bullets": []}
        for nearby in lines[i+1:i+10]:
            if nearby.startswith(("•", "-", "·")):
                entry["bullets"].append(nearby.lstrip("•-· ")[:300])
            elif entry["bullets"]:
                break
        experience.append(entry)
    normalized = normalize_text(text)
    detected = [name for name, aliases in pack.skill_aliases.items()
                if any(re.search(rf"(?<!\w){re.escape(normalize_text(alias))}(?!\w)", normalized) for alias in (name, *aliases))]
    extras: dict[str, list[dict]] = {key: [] for key in ("certifications", "projects", "languages")}
    for key, collected in extras.items():
        for line in sections.get(key, []):
            value = line.lstrip("•-· ")
            if key == "projects" and line.startswith(("•", "-", "·")) and collected:
                collected[-1]["description"] = (collected[-1].get("description", "") + " " + value).strip()[:300]
                continue
            if len(value) < 2 or re.fullmatch(r"[\d\s/–-]+", value):
                continue
            parts = re.split(r"\s+[|—]\s+|\s*:\s*", value, maxsplit=1)
            item = {"name": parts[0][:300]}
            if key == "languages":
                if len(parts) > 1:
                    item["level"] = parts[1][:300]
                else:
                    level = re.search(r"\b(nativo|basico|intermedio|avanzado|native|basic|intermediate|advanced|[abc][12])\b", normalize_text(value))
                    if level:
                        item["name"] = value[:level.start()].strip(" -–()")[:300]
                        item["level"] = value[level.start():level.end()]
            elif key == "projects":
                item["description"] = parts[1][:300] if len(parts) > 1 else ""
            else:
                if len(parts) > 1:
                    item["issuer"] = parts[1][:300]
                dates = dates_in(value)
                if dates and dates[0] != "actual":
                    item["date"] = dates[0]
            if item["name"]:
                collected.append(item)
    header = sections.get("header", [])
    headline = next((line for line in header if line != name and not re.search(r"[\d@:/|]", line)
                     and not re.search(r"curriculum|vitae", normalize_text(line))), "")
    return {"career_id": career_id, "name": name, "contact": contact, "education": education[:15],
            "experience": experience[:15], "detected_skills": detected, "source_name": Path(filename).name[:120],
            "headline": headline[:200], "summary": " ".join(sections.get("summary", []))[:600],
            **{key: value[:15] for key, value in extras.items()},
            "source_text": text[:MAX_TEXT], "warnings": ["Revisa los datos: el formato puede alterar el orden del texto. No se asignan niveles a las herramientas.",
            *([] if experience else ["No se separó la experiencia automáticamente; puedes añadirla o corregirla antes de guardar."])]}


def preview(data: bytes, filename: str, career_id: str) -> dict:
    draft = parse_text(extract_text(data, filename), career_id, filename)
    # Keep immutable originals locally; only a confirmed import makes one the current CV.
    source_id = hashlib.sha256(data).hexdigest() + Path(filename).suffix.lower()
    folder = cv_targets.data_dir() / "cv_imports"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = folder / source_id
    if not path.exists():
        with path.open("xb") as output:
            output.write(data)
        if os.name != "nt":
            path.chmod(0o600)
    return {**draft, "source_id": source_id, "base_revision": cv_profile.revision()}


def clean_draft(draft: dict) -> dict:
    if not isinstance(draft, dict) or len(json.dumps(draft)) > 160_000:
        raise ValueError("El borrador es demasiado grande.")
    pack = load_pack(str(draft.get("career_id", "")))
    name = draft.get("name", "")
    if not isinstance(name, str) or len(name) > 80:
        raise ValueError("El nombre admite hasta 80 caracteres.")
    from radar.profile_edit import _merge_contact

    contact = _merge_contact({}, draft.get("contact", {}))
    result = {"career_id": pack.id, "name": name.strip(), "contact": contact}
    for section in IMPORT_SECTIONS:
        entries = draft.get(section, [])
        if not isinstance(entries, list) or len(entries) > 15 or any(not isinstance(x, dict) for x in entries):
            raise ValueError("Revisa las secciones del CV (hasta 15 registros por sección).")
        result[section] = [cv_edit._clean(section, item) for item in entries]
    for key in ("headline", "summary"):
        value = draft.get(key, "")
        limit = 200 if key == "headline" else 600
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError("Revisa el titular y el resumen del CV.")
        result[key] = value.strip()
    for key, pattern in (("source_id", r"[a-f0-9]{64}\.(?:pdf|docx)"), ("base_revision", r"[a-f0-9]{64}")):
        value = draft.get(key, "")
        if value and (not isinstance(value, str) or not re.fullmatch(pattern, value)):
            raise ValueError("El archivo o la revisión del CV no son válidos.")
        result[key] = value
    detected = draft.get("detected_skills", [])
    if not isinstance(detected, list) or any(not isinstance(x, str) for x in detected):
        raise ValueError("Las herramientas deben ser una lista de nombres.")
    result["detected_skills"] = [name for name in detected if name in pack.skills]
    for key, limit in (("source_text", MAX_TEXT), ("source_name", 120)):
        value = draft.get(key, "")
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError("El texto del CV es demasiado grande.")
        result[key] = value
    return result


def save_draft(draft: dict) -> dict:
    result = clean_draft(draft)
    set_json_setting(DRAFT_KEY, result)
    return result


@cache
def _lock(path):
    return cv_profile.lock(str(cv_edit._path().resolve()))


def _merged(cv: dict, draft: dict) -> dict:
    result = json.loads(json.dumps(cv))
    if draft["name"]:
        result["name"] = draft["name"]
    result["contact"] = {**cv.get("contact", {}), **draft["contact"]}
    for key in ("headline", "summary"):
        if draft[key]:
            result[key] = draft[key]
    for section in IMPORT_SECTIONS:
        keys = cv_edit.LIST_SECTIONS[section][2]
        entries = list(result.get(section, []))
        for item in draft[section]:
            identity = tuple(normalize_text(item.get(k, "")) for k in keys)
            hits = [i for i, old in enumerate(entries) if tuple(normalize_text(old.get(k, "")) for k in keys) == identity]
            # Distinct dated jobs in the same role remain separate records.
            if section == "experience" and len(hits) == 1:
                old = entries[hits[0]]
                if old.get("from") and item.get("from") and old["from"] != item["from"] and old.get("to") != item.get("to"):
                    hits = []
            if len(hits) == 1:
                entries[hits[0]] = {**entries[hits[0]], **{k: v for k, v in item.items() if v}}
            else:
                entries.append(item)
        result[section] = entries
    result["detected_skills"] = sorted(set(cv.get("detected_skills", [])) | set(draft["detected_skills"]))
    return result


def changes(draft: dict) -> dict:
    """Preview the exact factual changes; absent imported sections never erase existing facts."""
    draft = clean_draft(draft)
    with cv_profile.lock(str(cv_edit._path().resolve())):
        cv = cv_edit._load() if cv_edit._path().exists() else {}
        merged = _merged(cv, draft)
        diff = {key: {"before": cv.get(key), "after": value} for key, value in merged.items() if cv.get(key) != value}
        return {"diff": diff, "revision": cv_profile.revision()}


def original() -> tuple[Path, str] | None:
    cv = cv_targets._read_json(cv_edit._path()) or {}
    source = cv.get("import_provenance") or {}
    source_id = source.get("source_id", "")
    if not isinstance(source_id, str) or not re.fullmatch(r"[a-f0-9]{64}\.(pdf|docx)", source_id):
        return None
    path = cv_targets.data_dir() / "cv_imports" / source_id
    return (path, Path(source.get("source_name") or "Mi CV" + path.suffix).name) if path.is_file() else None


def apply(draft: dict) -> dict:
    from radar.db.repository import recompute_scores

    draft = clean_draft(draft)
    if not draft["name"]:
        raise ValueError("Confirma tu nombre antes de guardar.")
    for section in IMPORT_SECTIONS:
        required = ("program",) if section == "education" else cv_edit.LIST_SECTIONS[section][1]
        if any(any(not item.get(key) for key in required) for item in draft[section]):
            raise ValueError("Completa o quita los registros incompletos antes de confirmar.")
    with _lock(str(database_path().resolve())):
        path = cv_edit._path()
        old = path.read_bytes() if path.exists() else None
        cv = cv_targets._read_json(path) or {}
        if old is not None and not cv:
            raise ValueError("El CV existente está dañado; restáuralo antes de importar.")
        merged = _merged(cv, draft)
        if draft["base_revision"] and draft["base_revision"] != cv_profile.revision() and merged != cv:
            raise cv_profile.ProfileConflict("Tu CV cambió mientras revisabas el archivo. Revisa de nuevo los cambios antes de confirmar.")
        cv = merged
        if draft["source_id"]:
            source = cv_targets.data_dir() / "cv_imports" / draft["source_id"]
            if not source.is_file():
                raise ValueError("Vuelve a adjuntar el archivo antes de confirmar.")
            cv["import_provenance"] = {"source_name": draft["source_name"], "source_id": draft["source_id"], "reviewed": True}
        try:
            with connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute("SELECT id FROM user_profile ORDER BY updated_at DESC LIMIT 1").fetchone()
                if row:
                    profile_id = row[0]
                    conn.execute("UPDATE user_profile SET name=%s,updated_at=now() WHERE id=%s", (draft["name"], profile_id))
                else:
                    profile_id = conn.execute("INSERT INTO user_profile(name,preferred_locations,education) VALUES (%s,%s,%s) RETURNING id",
                                              (draft["name"], '["Lima"]', "; ".join(" ".join((e.get("program", ""),e.get("status", ""))) for e in draft["education"]))).fetchone()[0]
                for key, value in (("career", draft["career_id"]), ("setup_completed_v1", "1")):
                    conn.execute("INSERT INTO app_settings(key,value) VALUES (%s,%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
                conn.execute("DELETE FROM app_settings WHERE key=%s", (DRAFT_KEY,))
                number = conn.execute("SELECT COALESCE(MAX(version_number),0)+1 FROM profile_versions WHERE profile_id=%s", (profile_id,)).fetchone()[0]
                conn.execute("INSERT INTO profile_versions(profile_id,version_number,snapshot,change_reason) VALUES (%s,%s,%s,%s)",
                             (profile_id, number, json.dumps({"name": draft["name"], "career_id": draft["career_id"], "education": cv["education"], "experience": cv["experience"]}), "confirmed CV setup"))
                backup = cv_edit._backup_and_write(cv)
        except Exception:
            if old is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(old)
            raise
    warnings = []
    try:
        recompute_scores(str(profile_id))
    except Exception:
        logging.getLogger(__name__).exception("Profile saved; score refresh failed")
        warnings.append("Perfil guardado; el recálculo quedó pendiente.")
    return {"saved": True, "career_id": draft["career_id"], "warnings": warnings,
            "undo": {"backup": backup, "revision": cv_profile.revision()} if old is not None else None}


def undo_import(backup: str, expected_revision: str) -> dict:
    """Restore a retained CV backup only while the reviewed import is still current."""
    if not isinstance(backup, str) or not re.fullmatch(r"cv_master\.json\.bak-\d{8}T\d{12}", backup):
        raise ValueError("La copia del CV no es válida.")
    with cv_profile.lock(str(cv_edit._path().resolve())):
        if expected_revision != cv_profile.revision():
            raise cv_profile.ProfileConflict("Tu CV cambió después de importar. Revisa tus datos antes de deshacer.")
        previous = cv_targets._read_json(cv_targets.data_dir() / backup)
        if previous is None:
            raise ValueError("La copia anterior ya no está disponible.")
        path = cv_edit._path()
        current = path.read_bytes()
        try:
            with connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("UPDATE user_profile SET name=%s,updated_at=now() WHERE id=(SELECT id FROM user_profile ORDER BY updated_at DESC LIMIT 1)",
                             (previous.get("name", ""),))
                cv_edit._backup_and_write(previous)
        except Exception:
            path.write_bytes(current)
            raise
    return {"saved": True, "warnings": cv_profile.refresh_scores()}


def status() -> dict:
    from radar.db.queries import get_profile

    return {"completed": bool(get_profile()), "draft": get_json_setting(DRAFT_KEY)}
