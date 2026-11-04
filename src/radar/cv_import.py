"""Local, bounded CV extraction and explicit, resumable profile setup."""
from __future__ import annotations

import io
import json
import logging
import re
import threading
import zipfile
from functools import cache
from pathlib import Path
from xml.etree import ElementTree

from radar import cv_edit, cv_targets
from radar.careers import load_pack
from radar.db.database import connection, database_path
from radar.normalize import normalize_text
from radar.requirements import qualification_aliases
from radar.settings import get_json_setting, set_json_setting

MAX_BYTES = 8 * 1024 * 1024
MAX_TEXT = 60_000
DRAFT_KEY = "setup_draft_v1"


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
    contact = {}
    email = re.search(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", text)
    phone = re.search(r"(?<!\d)(?:\+51[ -]?)?9(?:[ -]?\d){8}(?!\d)", text)
    if email:
        contact["email"] = email.group()
    if phone:
        contact["phone"] = phone.group()
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
        if norm.strip(": ") in {"educacion", "formacion", "formacion academica", "estudios", "educacion superior"}:
            academic = True
            continue
        if norm.strip(": ") in {"experiencia", "experiencia laboral", "experiencia profesional", "habilidades", "idiomas", "certificaciones"}:
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
        if norm in {"experiencia", "experiencia laboral", "experiencia profesional"}:
            section = "experience"
            continue
        if norm in {"educacion", "formacion", "formacion academica", "habilidades", "certificaciones", "idiomas"}:
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
        dates = dates_in(" ".join(lines[i+1:i+4]))
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
    return {"career_id": career_id, "name": name, "contact": contact, "education": education[:15],
            "experience": experience[:15], "detected_skills": detected, "source_name": Path(filename).name[:120],
            "source_text": text[:MAX_TEXT], "warnings": ["Revisa los datos: el formato puede alterar el orden del texto. No se asignan niveles a las herramientas.",
            *([] if experience else ["No se separó la experiencia automáticamente; puedes añadirla o corregirla antes de guardar."])]}


def preview(data: bytes, filename: str, career_id: str) -> dict:
    return parse_text(extract_text(data, filename), career_id, filename)


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
    for section in ("education", "experience"):
        entries = draft.get(section, [])
        if not isinstance(entries, list) or len(entries) > 15 or any(not isinstance(x, dict) for x in entries):
            raise ValueError("Revisa las secciones del CV (hasta 15 registros por sección).")
        result[section] = [cv_edit._clean(section, item) for item in entries]
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
    return threading.Lock()


def apply(draft: dict) -> dict:
    from radar.db.repository import recompute_scores

    draft = clean_draft(draft)
    if not draft["name"]:
        raise ValueError("Confirma tu nombre antes de guardar.")
    for section, required in (("education", ("program",)), ("experience", ("role", "company"))):
        if any(any(not item.get(key) for key in required) for item in draft[section]):
            raise ValueError("Completa o quita los registros incompletos antes de confirmar.")
    with _lock(str(database_path().resolve())):
        path = cv_edit._path()
        old = path.read_bytes() if path.exists() else None
        cv = cv_targets._read_json(path) or {}
        if old is not None and not cv:
            raise ValueError("El CV existente está dañado; restáuralo antes de importar.")
        cv.update(name=draft["name"], contact={**cv.get("contact", {}), **draft["contact"]})
        for section, identity in (("education", ("program", "institution")), ("experience", ("role", "company", "from"))):
            entries = list(cv.get(section, []))
            for item in draft[section]:
                key = tuple(normalize_text(item.get(k, "")) for k in identity)
                match = next((i for i, existing in enumerate(entries) if tuple(normalize_text(existing.get(k, "")) for k in identity) == key), None)
                if match is None:
                    entries.append(item)
                else:
                    entries[match] = {**entries[match], **{k: v for k, v in item.items() if v}}
            cv[section] = entries
        cv["detected_skills"] = sorted(set(cv.get("detected_skills", [])) | set(draft["detected_skills"]))
        cv["import_provenance"] = {"source_name": draft["source_name"], "reviewed": True}
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
                cv_edit._backup_and_write(cv)
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
    return {"saved": True, "career_id": draft["career_id"], "warnings": warnings}


def status() -> dict:
    from radar.db.queries import get_profile

    return {"completed": bool(get_profile()), "draft": get_json_setting(DRAFT_KEY)}
