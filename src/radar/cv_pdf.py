"""Escritor de PDF nativo para el CV (sin LibreOffice): una columna, texto real extraíble por los ATS.

Recibe los mismos bloques que ``cv_docx`` (ver ``cv_build``) y no tiene lógica de contenido. Usa una fuente TrueType del
sistema si la encuentra (Calibri/Arial en Windows y macOS, DejaVu/Liberation en Linux) para conservar tildes y símbolos;
si no, la fuente estándar Helvetica con los caracteres reducidos a Latin-1. Ver ``docs/cv.md``.
"""

from __future__ import annotations

import os
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from radar.cv_docx import Block

# (regular, negrita, cursiva) por plataforma, en orden de preferencia.
_FONT_SETS: tuple[tuple[str, str, str], ...] = (
    (r"C:\Windows\Fonts\calibri.ttf", r"C:\Windows\Fonts\calibrib.ttf", r"C:\Windows\Fonts\calibrii.ttf"),
    (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\ariali.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf", "/Library/Fonts/Arial Italic.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
     "/System/Library/Fonts/Supplemental/Arial Italic.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"),
    ("/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Oblique.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf"),
)
_LATIN1_FIXES = {"•": "-", "–": "-", "—": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "...", " ": " ", "→": "->"}
MARGIN_MM = 17.0


def find_fonts() -> tuple[str, str, str] | None:
    custom = os.getenv("RADAR_PDF_FONT")  # carpeta con regular.ttf, bold.ttf e italic.ttf (opcional)
    if custom:
        folder = Path(custom)
        trio = tuple(str(folder / name) for name in ("regular.ttf", "bold.ttf", "italic.ttf"))
        if all(Path(item).is_file() for item in trio):
            return trio  # type: ignore[return-value]
    return next((fonts for fonts in _FONT_SETS if all(Path(path).is_file() for path in fonts)), None)


def _latin1(text: str) -> str:
    for source, target in _LATIN1_FIXES.items():
        text = text.replace(source, target)
    return text.encode("latin-1", "replace").decode("latin-1")


class _Cv(FPDF):
    pass


def write_pdf(path: Path, blocks: list[Block], *, title: str, author: str = "", lang: str = "es-PE") -> tuple[Path, int]:
    """Escribe el PDF y devuelve su ruta y el número de páginas."""
    pdf = _Cv(format="A4", unit="mm")
    pdf.set_margins(MARGIN_MM, 15, MARGIN_MM)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_title(title)
    pdf.set_author(author)
    pdf.set_lang(lang)
    fonts = find_fonts()
    if fonts:
        pdf.add_font("cv", "", fonts[0])
        pdf.add_font("cv", "B", fonts[1])
        pdf.add_font("cv", "I", fonts[2])
        family, clean = "cv", (lambda text: text)
    else:
        family, clean = "Helvetica", _latin1
    pdf.add_page()
    width = pdf.w - 2 * MARGIN_MM

    def line(style: str, size: float, text: str, *, gap_before: float = 0, gap_after: float = 1.0, indent: float = 0, bullet: bool = False) -> None:
        pdf.set_font(family, style, size)
        pdf.set_x(MARGIN_MM + indent)
        if gap_before:
            pdf.ln(gap_before)
        if bullet:
            pdf.cell(4, size * 0.45, clean("-" if not fonts else "•"), new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.multi_cell(width - indent - 4, size * 0.45, clean(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.multi_cell(width - indent, size * 0.45, clean(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(gap_after)

    for block in blocks:
        kind, *texts = block
        text = texts[0] if texts else ""
        if kind == "name" and text:
            line("B", 20, text, gap_after=0.5)
        elif kind == "headline" and text:
            line("", 11, text, gap_after=0.5)
        elif kind == "contact" and text:
            line("", 9.5, text, gap_after=1.5)
        elif kind == "heading" and text:
            line("B", 10.5, text.upper(), gap_before=3.5, gap_after=0.4)
            y = pdf.get_y()
            pdf.set_draw_color(128, 128, 128)
            pdf.line(MARGIN_MM, y, MARGIN_MM + width, y)
            pdf.ln(1.5)
        elif kind == "entry" and text:
            line("B", 10.5, text, gap_before=1.5, gap_after=0.2)
            if len(texts) > 1 and texts[1]:
                line("I", 9.5, texts[1], gap_after=0.6)
        elif kind == "bullet" and text:
            line("", 10, text, indent=2, bullet=True, gap_after=0.5)
        elif kind == "para" and text:
            line("", 10, text, gap_after=1.0)
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
    return path, pdf.page
