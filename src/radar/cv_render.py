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
    "sidebar": {"label": "Moderna ejecutiva con foto", "photo": True},
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
    header = selection["header"]
    left_m = 16.0
    right_m = 14.0
    full_w = PAGE_W - left_m - right_m
    pdf.set_margins(left_m, 14.0, right_m)
    pdf.set_auto_page_break(True, margin=BOTTOM)
    pdf.set_xy(left_m, 14.0)

    photo_size = 32.0
    text_w = full_w - photo_size - 6.0 if photo is not None else full_w

    writer.line("B", 20, header["name"], line_id="name", gap_after=0.8, color=accent, width=text_w)
    if header["headline"]:
        writer.line("", 10.5, header["headline"], line_id="headline", gap_after=2.0, color=(70, 70, 70), width=text_w)

    contact_parts = [part.strip() for part in header["contact"].split("·") if part.strip()]
    if contact_parts:
        c1_parts = [p for p in contact_parts if not ("linkedin.com" in p or "github.com" in p)]
        c2_parts = [p for p in contact_parts if "linkedin.com" in p or "github.com" in p]
        if c1_parts:
            writer.line("", 8.5, "  ·  ".join(c1_parts), gap_after=1.0, color=(80, 80, 80), width=text_w)
        if c2_parts:
            writer.line("", 8.5, "  ·  ".join(c2_parts), gap_after=2.0, color=(80, 80, 80), width=text_w)

    if photo is not None:
        x_photo = PAGE_W - right_m - photo_size
        with pdf.elliptic_clip(x_photo, 14.0, photo_size, photo_size):
            pdf.image(_square_photo(photo), x=x_photo, y=14.0, w=photo_size, h=photo_size)
        pdf.set_y(max(pdf.get_y(), 14.0 + photo_size + 3.0))

    writer.rule(accent)

    def heading(text: str) -> None:
        writer.line("B", 10.5, text.upper(), gap_before=3.0, gap_after=0.4, color=accent)
        writer.rule(accent)

    if selection["summary"]:
        heading(labels["summary"])
        writer.line("", 9.2, selection["summary"], line_id="summary", gap_after=1.5)

    if selection["skills"]:
        heading(labels["skills"])
        writer.line("", 9.0, " • ".join(selection["skills"]), gap_after=1.5)

    if selection["experience"]:
        heading(labels["experience"])
        for role in selection["experience"]:
            writer.line("B", 10.0, role["title"], line_id=role["id"], gap_before=2.0, gap_after=0.2)
            if role.get("detail"):
                writer.line("I", 8.8, role["detail"], gap_after=0.6, color=(90, 90, 90))
            for b in role["bullets"]:
                writer.line("", 9.0, b["text"], line_id=b["id"], indent=3.0, bullet=True, gap_after=0.6)

    if selection["projects"]:
        heading(labels["projects"])
        for project in selection["projects"]:
            writer.line("B", 10.0, project["title"], line_id=project["id"], gap_before=2.0, gap_after=0.2)
            if project.get("detail"):
                writer.line("I", 8.8, project["detail"], gap_after=0.6, color=(90, 90, 90))
            for b in project["bullets"]:
                writer.line("", 9.0, b["text"], line_id=b["id"], indent=3.0, bullet=True, gap_after=0.6)

    if selection["education"]:
        heading(labels["education"])
        for edu in selection["education"]:
            writer.line("B", 9.8, edu["title"], line_id=edu["id"], gap_before=1.5, gap_after=0.2)
            if edu.get("detail"):
                writer.line("I", 8.8, edu["detail"], gap_after=0.6, color=(90, 90, 90))

    if selection["certifications"]:
        heading(labels["certifications"])
        for cert in selection["certifications"]:
            writer.line("B", 9.2, cert["title"], line_id=cert["id"], gap_before=1.2, gap_after=0.1)
            if cert.get("detail"):
                writer.line("I", 8.5, cert["detail"], gap_after=0.4, color=(90, 90, 90))

    if selection["languages"]:
        heading(labels["languages"])
        writer.line("", 9.0, ", ".join(selection["languages"]), gap_after=1.0)


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
        pdf.full_left, pdf.reset_after_first = 16.0, False
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
