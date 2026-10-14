"""Carpeta por postulación: el CV exportado, una copia de la oferta y el registro de lo que enviaste.

La subida a los portales es manual, así que cada postulación vive en una carpeta visible y fácil de encontrar:

    <raíz>/2026-10-14 Empresa - Puesto/
        CV Nombre - Puesto.pdf          (el archivo que ve el reclutador: tu nombre y el puesto, sin códigos)
        oferta.md                       (copia de la oferta: las ofertas desaparecen)
        postulacion.json                (versión, plantilla, hash, estado)
        anteriores/                     (versiones previas del CV, nunca se pierden)

Radar nunca envía una postulación: prepara los archivos y, cuando confirmas, la registra en tu seguimiento. Ver
``docs/design-cv-studio.md``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from platformdirs import user_documents_dir

from radar import cv_build, cv_doc, cv_docx, cv_targets
from radar.db.database import connection
from radar.db.repository import track_application
from radar.settings import get_setting, set_setting

DEFAULT_PATTERN = "CV {nombre} - {puesto}"
ALLOWED_SUFFIXES = {".pdf", ".docx", ".md", ".json"}
FORMATS = ("pdf", "docx")
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
_PLACEHOLDERS = {"nombre", "puesto", "empresa", "fecha"}


def _today() -> str:
    """Fecha local de hoy (es la que ves en tu calendario, no la UTC)."""
    return datetime.now(UTC).astimezone().date().isoformat()


def safe_name(text: str, limit: int = 80, ascii_only: bool = False) -> str:
    """Nombre de archivo o carpeta válido en Windows, macOS y Linux."""
    value = unicodedata.normalize("NFKC", text or "")
    if ascii_only:
        value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = _FORBIDDEN.sub(" ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    value = value[:limit].strip(" .")
    if value.lower().split(".")[0] in _RESERVED:
        value = f"{value}_"
    return value or "sin nombre"


def short_role(title: str) -> str:
    """Puesto corto para el nombre del archivo: sin paréntesis, marcas de género ni exceso de largo."""
    cleaned = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", title or "")
    cleaned = re.sub(r"\s*[-–|/]\s*(lima|remoto|h[ií]brido|presencial).*$", "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip(" -–|") or (title or "Puesto")


# --- ajustes --------------------------------------------------------------------------------------


def default_root() -> Path:
    return Path(user_documents_dir()) / "Radar" / "Postulaciones"


def export_root() -> Path:
    raw = get_setting("cv_export_dir")
    return Path(raw).expanduser() if raw else default_root()


def filename_pattern() -> str:
    return get_setting("cv_filename_pattern") or DEFAULT_PATTERN


def ascii_names() -> bool:
    return get_setting("cv_ascii_filenames", "1") != "0"


def settings() -> dict[str, Any]:
    return {"export_dir": str(export_root()), "default_export_dir": str(default_root()), "filename_pattern": filename_pattern(),
            "ascii_filenames": ascii_names(), "placeholders": sorted(_PLACEHOLDERS), "example": _example_name()}


def _example_name() -> str:
    return safe_name(filename_pattern().format(nombre="Ana Pérez", puesto="Analista BI", empresa="Empresa SAC", fecha="2026-10-14"),
                     ascii_only=ascii_names())


def update_settings(export_dir: str | None = None, filename_pattern_: str | None = None, ascii_filenames: bool | None = None) -> dict[str, Any]:
    if export_dir is not None:
        path = Path(export_dir).expanduser()
        if not path.is_absolute():
            raise ValueError("La carpeta debe ser una ruta absoluta")
        home = Path.home().resolve()
        resolved = path.resolve()
        if home not in resolved.parents and resolved != home:
            raise ValueError("Elige una carpeta dentro de tu carpeta personal")
        if resolved == home or cv_targets.data_dir().resolve() in (resolved, *resolved.parents):
            raise ValueError("Elige una subcarpeta propia (no tu carpeta personal ni la carpeta de datos de Radar)")
        set_setting("cv_export_dir", str(resolved))
    if filename_pattern_ is not None:
        found = set(re.findall(r"\{(\w+)\}", filename_pattern_))
        if not found or not found <= _PLACEHOLDERS or len(filename_pattern_) > 80 or re.search(r"[<>:\"/\\|?*]", filename_pattern_):
            raise ValueError("El patrón usa {nombre}, {puesto}, {empresa} y {fecha}, máximo 80 caracteres, sin / \\ : * ? \" < > |")
        set_setting("cv_filename_pattern", filename_pattern_)
    if ascii_filenames is not None:
        set_setting("cv_ascii_filenames", "1" if ascii_filenames else "0")
    return settings()


# --- exportación -----------------------------------------------------------------------------------


def _job_info(job_id: str) -> dict[str, Any]:
    with connection() as conn:
        row = conn.execute(
            """SELECT j.title, c.name, j.location, j.published_at, j.work_mode, j.salary_min, j.salary_max, j.salary_currency,
                      COALESCE(j.description_clean, j.description_raw),
                      (SELECT source_url FROM job_sources s WHERE s.job_id=j.id ORDER BY s.last_seen_at DESC LIMIT 1)
               FROM jobs j LEFT JOIN companies c ON c.id=j.company_id WHERE j.id=%s""", (job_id,)).fetchone()
    if row is None:
        raise ValueError(f"Oferta no encontrada: {job_id}")
    return {"title": row[0], "company": row[1] or "Empresa", "location": row[2], "published_at": str(row[3] or ""), "work_mode": row[4],
            "salary": f"{row[5]}–{row[6]} {row[7]}" if row[5] or row[6] else None, "description": row[8] or "", "url": row[9]}


def _offer_markdown(info: dict[str, Any]) -> str:
    lines = [f"# {info['title']}", "", f"- **Empresa:** {info['company']}", f"- **Ubicación:** {info['location'] or '—'}",
             f"- **Publicada:** {info['published_at'][:10] or '—'}", f"- **Modalidad:** {info['work_mode'] or '—'}",
             f"- **Salario publicado:** {info['salary'] or '—'}", f"- **Enlace original:** {info['url'] or '—'}",
             f"- **Copia guardada:** {_today()} (las ofertas desaparecen; esta es la versión que viste)", "",
             "## Descripción", "", info["description"].strip() or "(sin descripción)", ""]
    return "\n".join(lines)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _existing_folder(job_id: str) -> Path | None:
    with connection() as conn:
        row = conn.execute("SELECT folder FROM application_packages WHERE job_id=%s", (job_id,)).fetchone()
    return Path(row[0]) if row else None


def _new_folder(job_id: str, info: dict[str, Any]) -> Path:
    base = safe_name(f"{_today()} {info['company']} - {short_role(info['title'])}", 90, ascii_names())
    root = export_root()
    folder, count = root / base, 1
    while folder.exists():
        count += 1
        folder = root / f"{base} ({count})"
    folder.mkdir(parents=True, exist_ok=False)
    return folder


def _archive(folder: Path, name: str) -> None:
    current = folder / name
    if current.exists():
        old = folder / "anteriores"
        old.mkdir(exist_ok=True)
        stamp = datetime.fromtimestamp(current.stat().st_mtime, tz=UTC).astimezone().strftime("%Y%m%d-%H%M%S")
        shutil.move(str(current), str(old / f"{current.stem} {stamp}{current.suffix}"))


def export(job_id: str, formats: list[str] | None = None) -> dict[str, Any]:
    """Escribe el CV vigente del estudio en la carpeta de la postulación (la crea la primera vez) y la registra."""
    wanted = [f for f in (formats or ["pdf"]) if f in FORMATS]
    if not wanted:
        raise ValueError(f"formats debe incluir alguno de: {', '.join(FORMATS)}")
    doc = cv_doc.get_document(job_id)
    final, _ = cv_doc._final(doc)
    pdf, pages = cv_doc.pdf_bytes(job_id)
    info = _job_info(job_id)
    folder = _existing_folder(job_id)
    if folder is None or not folder.exists():
        folder = _new_folder(job_id, info)
    stem = safe_name(filename_pattern().format(nombre=final["header"]["name"] or "CV", puesto=short_role(info["title"]),
                                               empresa=info["company"], fecha=_today()),
                     80, ascii_names())
    files: list[dict[str, Any]] = []
    if "pdf" in wanted:
        _archive(folder, f"{stem}.pdf")
        (folder / f"{stem}.pdf").write_bytes(pdf)
        files.append({"name": f"{stem}.pdf", "format": "pdf", "size": len(pdf), "sha256": _sha(pdf), "pages": pages})
    if "docx" in wanted:
        _archive(folder, f"{stem}.docx")
        cv_docx.write_docx(folder / f"{stem}.docx", cv_build.to_blocks(final), title=f"CV {final['header']['name']}",
                           author=final["header"]["name"], lang="en-US" if final["language"] == "en" else "es-PE")
        data = (folder / f"{stem}.docx").read_bytes()
        files.append({"name": f"{stem}.docx", "format": "docx", "size": len(data), "sha256": _sha(data), "pages": None})
    (folder / "oferta.md").write_text(_offer_markdown(info), encoding="utf-8")
    profile_file = cv_targets.data_dir() / "cv_master.json"
    manifest = {
        "job_id": job_id, "exported_at": datetime.now(UTC).isoformat(timespec="seconds"), "job": {k: info[k] for k in ("title", "company", "url")},
        "template": doc["template"], "photo": doc["photo"], "language": final["language"], "pages": pages, "pages_budget": final["pages_budget"],
        "operations": len(doc["ops"]), "edited_lines": sorted(final.get("edits", {})), "files": files, "warnings": final["warnings"],
        "profile_sha256": _sha(profile_file.read_bytes()) if profile_file.exists() else None,
    }
    (folder / "postulacion.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with connection() as conn:
        conn.execute(
            """INSERT INTO application_packages(job_id, folder, files, exported_at) VALUES (%s,%s,%s,now())
               ON CONFLICT(job_id) DO UPDATE SET folder=EXCLUDED.folder, files=EXCLUDED.files, exported_at=now(), updated_at=now()""",
            (job_id, str(folder), json.dumps(files)))
    return {"folder": str(folder), "files": files, "pages": pages, "warnings": final["warnings"], "over_budget": pages > final["pages_budget"],
            "package": package(job_id)}


# --- consulta y acciones ---------------------------------------------------------------------------


def package(job_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute(
            """SELECT p.id, p.job_id, p.folder, p.files, p.status, p.notes, p.exported_at, p.applied_at, j.title, c.name
               FROM application_packages p JOIN jobs j ON j.id=p.job_id LEFT JOIN companies c ON c.id=j.company_id WHERE p.job_id=%s""",
            (job_id,)).fetchone()
    return _row(row) if row else None


def _row(row: Any) -> dict[str, Any]:
    folder = Path(row[2])
    files = json.loads(row[3])
    for item in files:
        path = folder / item["name"]
        item["exists"] = path.is_file()
        item["modified_after_export"] = bool(path.is_file() and _sha(path.read_bytes()) != item["sha256"])
    return {"id": row[0], "job_id": row[1], "folder": row[2], "folder_exists": folder.is_dir(), "files": files, "status": row[4],
            "notes": row[5], "exported_at": row[6], "applied_at": row[7], "title": row[8], "company": row[9]}


def list_packages(limit: int = 100) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """SELECT p.id, p.job_id, p.folder, p.files, p.status, p.notes, p.exported_at, p.applied_at, j.title, c.name
               FROM application_packages p JOIN jobs j ON j.id=p.job_id LEFT JOIN companies c ON c.id=j.company_id
               ORDER BY COALESCE(p.applied_at, p.exported_at) DESC LIMIT %s""", (min(max(limit, 1), 500),)).fetchall()
    return [_row(r) for r in rows]


def mark_applied(job_id: str, notes: str | None = None) -> dict[str, Any]:
    """Tú ya enviaste la postulación en el portal: se registra aquí y en tu seguimiento."""
    found = package(job_id)
    if found is None:
        raise ValueError("Primero prepara la postulación (exporta el CV)")
    track_application(job_id, "applied", notes)
    with connection() as conn:
        conn.execute("UPDATE application_packages SET status='applied', applied_at=COALESCE(applied_at, now()), notes=COALESCE(%s, notes), updated_at=now() WHERE job_id=%s",
                     (notes, job_id))
    return package(job_id) or found


def file_path(job_id: str, name: str) -> Path | None:
    """Archivo de la carpeta de la postulación, solo por nombre simple y con extensión permitida."""
    found = package(job_id)
    if found is None or name != Path(name).name or Path(name).suffix.lower() not in ALLOWED_SUFFIXES:
        return None
    path = Path(found["folder"]) / name
    return path if path.is_file() else None


def _launch(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def open_folder(job_id: str) -> dict[str, Any]:
    found = package(job_id)
    if found is None or not found["folder_exists"]:
        raise ValueError("La carpeta de esta postulación no existe todavía o fue movida")
    _launch(Path(found["folder"]))
    return {"opened": found["folder"]}
