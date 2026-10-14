"""Renderizador del CV con plantillas definidas como datos y mapa de clics.

El estudio muestra exactamente el PDF que se exporta: este módulo escribe ese PDF a partir de la selección final (ver
``cv_doc``) y devuelve además, por cada línea, su página y su caja en milímetros (``boxes``), con lo que un clic en la página
selecciona la línea de origen. Dos plantillas: ``ats`` (una columna, sin foto, a prueba de filtros de portales) y ``sidebar``
(barra lateral con foto opcional). Ver ``docs/design-cv-studio.md``.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image

from radar.cv_pdf import _latin1, find_fonts

PAGE_W, PAGE_H = 210.0, 297.0
TEMPLATES = {
    "ats": {"label": "Sobria (una columna, sin foto)", "photo": False},
    "sidebar": {"label": "Barra lateral con foto", "photo": True},
}
LABELS = {
    "es": {"contact": "Contacto", "skills": "Habilidades", "languages": "Idiomas", "education": "Formación",
           "summary": "Perfil", "experience": "Experiencia", "projects": "Proyectos", "certifications": "Certificaciones"},
    "en": {"contact": "Contact", "skills": "Skills", "languages": "Languages", "education": "Education",
           "summary": "Summary", "experience": "Experience", "projects": "Projects", "certifications": "Certifications"},
}
SIDEBAR_W = 62.0
SIDEBAR_PAD = 7.0
MAIN_LEFT = SIDEBAR_W + 9.0
MARGIN = 17.0
RIGHT = 14.0
BOTTOM = 14.0


@dataclass
class Rendered:
    pdf: bytes
    pages: int
    boxes: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    template: str = "ats"


class _Doc(FPDF):
    full_left = MARGIN
    reset_after_first = False

    def header(self) -> None:
        if self.reset_after_first and self.page_no() > 1:
            self.set_left_margin(self.full_left)
            self.set_right_margin(RIGHT)
            self.set_x(self.full_left)


class _Writer:
    def __init__(self, pdf: _Doc, fonts: tuple[str, str, str] | None) -> None:
        self.pdf = pdf
        self.boxes: list[dict[str, Any]] = []
        if fonts:
            pdf.add_font("cv", "", fonts[0])
            pdf.add_font("cv", "B", fonts[1])
            pdf.add_font("cv", "I", fonts[2])
            self.family, self.clean, self.bullet = "cv", (lambda text: text), "•"
        else:
            self.family, self.clean, self.bullet = "Helvetica", _latin1, "-"

    def _record(self, line_id: str | None, start_page: int, start_y: float, x: float, width: float) -> None:
        if not line_id:
            return
        end_page, end_y = self.pdf.page, self.pdf.get_y()
        if end_page == start_page:
            self.boxes.append({"id": line_id, "page": start_page, "x": x, "y": start_y, "w": width, "h": max(end_y - start_y, 1.0)})
            return
        self.boxes.append({"id": line_id, "page": start_page, "x": x, "y": start_y, "w": width, "h": max(PAGE_H - BOTTOM - start_y, 1.0)})
        self.boxes.append({"id": line_id, "page": end_page, "x": x, "y": 15.0, "w": width, "h": max(end_y - 15.0, 1.0)})

    def line(self, style: str, size: float, text: str, *, line_id: str | None = None, gap_before: float = 0.0,
             gap_after: float = 1.0, indent: float = 0.0, bullet: bool = False, color: tuple[int, int, int] = (0, 0, 0),
             width: float | None = None) -> None:
        pdf = self.pdf
        pdf.set_font(self.family, style, size)
        pdf.set_text_color(*color)
        if gap_before:
            pdf.ln(gap_before)
        left = pdf.l_margin + indent
        total = width if width is not None else pdf.w - pdf.l_margin - pdf.r_margin - indent
        pdf.set_x(left)
        page, y = pdf.page, pdf.get_y()
        if bullet:
            pdf.cell(4, size * 0.45, self.clean(self.bullet), new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.multi_cell(total - 4, size * 0.45, self.clean(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        else:
            pdf.multi_cell(total, size * 0.45, self.clean(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        self._record(line_id, page, y, left, total)
        pdf.ln(gap_after)

    def rule(self, color: tuple[int, int, int] = (128, 128, 128)) -> None:
        pdf = self.pdf
        y = pdf.get_y()
        pdf.set_draw_color(*color)
        pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
        pdf.ln(1.5)


def _square_photo(path: Path) -> io.BytesIO:
    with Image.open(path) as image:
        image = image.convert("RGB")
        side = min(image.size)
        left, top = (image.width - side) // 2, (image.height - side) // 3  # sesgo hacia arriba: rostro
        image = image.crop((left, max(top, 0), left + side, max(top, 0) + side)).resize((400, 400))
        out = io.BytesIO()
        image.save(out, "JPEG", quality=88)
        out.seek(0)
        return out


def _role_blocks(writer: _Writer, selection: dict[str, Any], labels: dict[str, str], accent: tuple[int, int, int]) -> None:
    def heading(text: str) -> None:
        writer.line("B", 10.5, text.upper(), gap_before=3.5, gap_after=0.4, color=accent)
        writer.rule((accent[0], accent[1], accent[2]) if accent != (0, 0, 0) else (128, 128, 128))

    if selection["summary"]:
        heading(labels["summary"])
        writer.line("", 10, selection["summary"], line_id="summary", gap_after=1.0)
    if selection["experience"]:
        heading(labels["experience"])
        for role in selection["experience"]:
            writer.line("B", 10.5, role["title"], line_id=role["id"], gap_before=1.5, gap_after=0.2)
            if role["detail"]:
                writer.line("I", 9.5, role["detail"], gap_after=0.6)
            for bullet in role["bullets"]:
                writer.line("", 10, bullet["text"], line_id=bullet["id"], indent=2, bullet=True, gap_after=0.5)
    if selection["projects"]:
        heading(labels["projects"])
        for project in selection["projects"]:
            writer.line("B", 10.5, project["title"], line_id=project["id"], gap_before=1.5, gap_after=0.2)
            if project["detail"]:
                writer.line("I", 9.5, project["detail"], gap_after=0.6)
            for bullet in project["bullets"]:
                writer.line("", 10, bullet["text"], line_id=bullet["id"], indent=2, bullet=True, gap_after=0.5)


def _render_ats(writer: _Writer, selection: dict[str, Any], labels: dict[str, str]) -> None:
    header = selection["header"]
    if header["name"]:
        writer.line("B", 20, header["name"], line_id="name", gap_after=0.5)
    if header["headline"]:
        writer.line("", 11, header["headline"], line_id="headline", gap_after=0.5)
    if header["contact"]:
        writer.line("", 9.5, header["contact"], gap_after=1.5)
    _role_blocks(writer, selection, labels, (0, 0, 0))
    if selection["education"]:
        writer.line("B", 10.5, labels["education"].upper(), gap_before=3.5, gap_after=0.4)
        writer.rule()
        for item in selection["education"]:
            writer.line("B", 10.5, item["title"], line_id=item["id"], gap_before=1.5, gap_after=0.2)
            if item["detail"]:
                writer.line("I", 9.5, item["detail"], gap_after=0.6)
    if selection["certifications"]:
        writer.line("B", 10.5, labels["certifications"].upper(), gap_before=3.5, gap_after=0.4)
        writer.rule()
        for item in selection["certifications"]:
            writer.line("B", 10.5, item["title"], line_id=item["id"], gap_before=1.5, gap_after=0.2)
            if item["detail"]:
                writer.line("I", 9.5, item["detail"], gap_after=0.6)
    for key, values in (("skills", selection["skills"]), ("languages", selection["languages"])):
        if values:
            writer.line("B", 10.5, labels[key].upper(), gap_before=3.5, gap_after=0.4)
            writer.rule()
            writer.line("", 10, ", ".join(values), gap_after=1.0)


def _render_sidebar(writer: _Writer, selection: dict[str, Any], labels: dict[str, str], photo: Path | None,
                    warnings: list[str]) -> None:
    pdf = writer.pdf
    accent = (38, 70, 83)
    pdf.set_fill_color(238, 241, 244)
    pdf.rect(0, 0, SIDEBAR_W, PAGE_H, style="F")
    pdf.set_auto_page_break(False)
    pdf.set_left_margin(SIDEBAR_PAD)
    pdf.set_right_margin(PAGE_W - SIDEBAR_W + SIDEBAR_PAD)
    pdf.set_xy(SIDEBAR_PAD, 12)
    inner = SIDEBAR_W - 2 * SIDEBAR_PAD
    if photo is not None:
        size = 36.0
        x = (SIDEBAR_W - size) / 2
        with pdf.elliptic_clip(x, 12, size, size):
            pdf.image(_square_photo(photo), x=x, y=12, w=size, h=size)
        pdf.set_y(12 + size + 6)

    def fits(text: str, size: float) -> bool:
        pdf.set_font(writer.family, "", size)
        height = pdf.multi_cell(inner, size * 0.45, writer.clean(text), dry_run=True, output="HEIGHT")
        return pdf.get_y() + height < PAGE_H - BOTTOM

    def section(title: str, rows: list[tuple[str | None, str, str]]) -> None:
        if not rows:
            return
        writer.line("B", 9.5, title.upper(), gap_before=3.0, gap_after=1.0, color=accent, width=inner)
        for line_id, text, style in rows:
            if not fits(text, 9):
                warnings.append(f"La barra lateral no tiene espacio para «{text[:40]}»; se omitió en la página.")
                return
            writer.line(style, 9, text, line_id=line_id, gap_after=1.2, width=inner)

    contact = [part.strip() for part in selection["header"]["contact"].split("·") if part.strip()]
    section(labels["contact"], [(None, part, "") for part in contact])
    section(labels["skills"], [(None, skill, "") for skill in selection["skills"]])
    section(labels["languages"], [(None, language, "") for language in selection["languages"]])
    section(labels["education"], [(item["id"], item["title"] + (f"\n{item['detail']}" if item["detail"] else ""), "") for item in selection["education"]])

    pdf.set_auto_page_break(True, margin=BOTTOM)
    pdf.set_left_margin(MAIN_LEFT)
    pdf.set_right_margin(RIGHT)
    pdf.set_xy(MAIN_LEFT, 14)
    header = selection["header"]
    writer.line("B", 22, header["name"], line_id="name", gap_after=0.5, color=accent)
    if header["headline"]:
        writer.line("", 11, header["headline"], line_id="headline", gap_after=1.5, color=(70, 70, 70))
    _role_blocks(writer, selection, labels, accent)
    if selection["certifications"]:
        writer.line("B", 10.5, labels["certifications"].upper(), gap_before=3.5, gap_after=0.4, color=accent)
        writer.rule(accent)
        for item in selection["certifications"]:
            writer.line("B", 10, item["title"], line_id=item["id"], gap_before=1.0, gap_after=0.1)
            if item["detail"]:
                writer.line("I", 9, item["detail"], gap_after=0.5)


def render(selection: dict[str, Any], template: str = "ats", photo: Path | None = None) -> Rendered:
    """Escribe el PDF de la selección y devuelve bytes, páginas y la caja de cada línea."""
    if template not in TEMPLATES:
        raise ValueError(f"Plantilla desconocida: {template}")
    labels = LABELS[selection.get("language", "es")]
    pdf = _Doc(format="A4", unit="mm")
    pdf.set_title(f"CV {selection['header']['name']}")
    pdf.set_author(selection["header"]["name"])
    pdf.set_lang("en-US" if selection.get("language") == "en" else "es-PE")
    writer = _Writer(pdf, find_fonts())
    warnings: list[str] = []
    pdf.set_auto_page_break(True, margin=BOTTOM)
    if template == "sidebar":
        pdf.full_left, pdf.reset_after_first = MARGIN, True
        pdf.add_page()
        _render_sidebar(writer, selection, labels, photo if TEMPLATES[template]["photo"] else None, warnings)
    else:
        pdf.set_margins(MARGIN, 15, RIGHT)
        pdf.add_page()
        _render_ats(writer, selection, labels)
    return Rendered(bytes(pdf.output()), pdf.page, writer.boxes, warnings, template)


def page_png(pdf: bytes, page: int = 1, scale: float = 1.4) -> bytes:
    """Imagen PNG de una página del PDF (la vista previa del estudio)."""
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(pdf)
    try:
        if not 1 <= page <= len(document):
            raise ValueError(f"La página {page} no existe (hay {len(document)})")
        image = document[page - 1].render(scale=scale).to_pil()
    finally:
        document.close()
    out = io.BytesIO()
    image.save(out, "PNG", optimize=False)
    return out.getvalue()
