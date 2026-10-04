#!/usr/bin/env python3
"""Markdown-Rechtstexte als druckfreundliche A4-PDF erzeugen.

Laeuft automatisch per GitHub Action (.github/workflows/rechtstexte-pdf.yml),
sobald sich agb.md, datenschutz.md oder impressum.md aendern. Gleicher Text
ergibt byte-gleiche PDFs (reportlab "invariant"), damit Programme, die die PDF
per Link auf Aenderungen pruefen (z. B. Partdock), nur echte Aenderungen sehen.

Erforderliche Schriftdateien im Unterordner fonts/:
    SourceSerif4-Regular.ttf
    SourceSerif4-Semibold.ttf
    SourceSans3-Regular.ttf
    SourceSans3-Semibold.ttf

Voraussetzung:
    py -m pip install reportlab
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PAGE_WIDTH, _ = A4
MARGIN = 2 * cm
SCRIPT_DIR = Path(__file__).resolve().parent / "fonts"
# Ohne Zeitstempel/Zufalls-ID: gleicher Text -> identische PDF.
rl_config.invariant = 1
DEFAULT_FOOTER = "HMNX.Prints · Stephan Peter · Stand: 09/2026"

SERIF = "SourceSerif4-Regular"
SERIF_SEMIBOLD = "SourceSerif4-Semibold"
SANS = "SourceSans3-Regular"
SANS_SEMIBOLD = "SourceSans3-Semibold"


def register_fonts() -> None:
    files = {
        SERIF: SCRIPT_DIR / "SourceSerif4-Regular.ttf",
        SERIF_SEMIBOLD: SCRIPT_DIR / "SourceSerif4-Semibold.ttf",
        SANS: SCRIPT_DIR / "SourceSans3-Regular.ttf",
        SANS_SEMIBOLD: SCRIPT_DIR / "SourceSans3-Semibold.ttf",
    }
    missing = [path.name for path in files.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Fehlende Schriftdateien:\n- " + "\n- ".join(missing))

    for font_name, font_path in files.items():
        pdfmetrics.registerFont(TTFont(font_name, str(font_path)))

    pdfmetrics.registerFontFamily(SERIF, normal=SERIF, bold=SERIF_SEMIBOLD, italic=SERIF, boldItalic=SERIF_SEMIBOLD)
    pdfmetrics.registerFontFamily(SANS, normal=SANS, bold=SANS_SEMIBOLD, italic=SANS, boldItalic=SANS_SEMIBOLD)


def escape_xml(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _link(match) -> str:
    text, url = match.group(1), match.group(2)
    # Verweise auf andere .md-Dateien im Repository: nur der Text.
    if url.startswith(("http://", "https://", "mailto:")):
        return f'<a href="{url}" color="#1d4ed8">{text}</a>'
    return text


def inline(value: str) -> str:
    value = escape_xml(value.strip())
    # Einfache HTML-Auszeichnungen aus GitHub-Markdown (<sub>, <br> ...) entfernen.
    value = re.sub(r"&lt;br\s*/?&gt;", " ", value)
    value = re.sub(r"&lt;/?(sub|sup|small|span|div|p)\b[^&]*&gt;", "", value)
    value = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", _link, value)
    value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"`(.+?)`", r'<font name="Courier">\1</font>', value)
    return value


def is_table_separator(value: str) -> bool:
    return bool(re.fullmatch(r"\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?", value.strip()))


def styles():
    result = getSampleStyleSheet()
    result.add(ParagraphStyle(name="DocTitle", parent=result["Title"], fontName=SERIF_SEMIBOLD, fontSize=17, leading=21, alignment=TA_CENTER, spaceAfter=12))
    result.add(ParagraphStyle(name="H1", parent=result["Heading1"], fontName=SERIF_SEMIBOLD, fontSize=13, leading=16, spaceBefore=12, spaceAfter=7, keepWithNext=True))
    result.add(ParagraphStyle(name="H2", parent=result["Heading2"], fontName=SERIF_SEMIBOLD, fontSize=11.2, leading=13.8, spaceBefore=9, spaceAfter=5, keepWithNext=True))
    result.add(ParagraphStyle(name="H3", parent=result["Heading3"], fontName=SERIF_SEMIBOLD, fontSize=10.2, leading=12.8, spaceBefore=8, spaceAfter=4, keepWithNext=True))
    result.add(ParagraphStyle(name="Body", parent=result["BodyText"], fontName=SERIF, fontSize=10, leading=13.2, spaceAfter=5.5, splitLongWords=False))
    result.add(ParagraphStyle(name="List", parent=result["BodyText"], fontName=SERIF, fontSize=10, leading=13.2, leftIndent=16, firstLineIndent=-10, spaceAfter=3.5, splitLongWords=False))
    result.add(ParagraphStyle(name="Table", parent=result["BodyText"], fontName=SANS, fontSize=8.6, leading=10.8, splitLongWords=False))
    result.add(ParagraphStyle(name="TableHead", parent=result["BodyText"], fontName=SANS_SEMIBOLD, fontSize=8.6, leading=10.8, splitLongWords=False))
    return result


def make_table(headers: list[str], rows: list[list[str]], style_set) -> Table:
    count = len(headers)
    width = PAGE_WIDTH - 2 * MARGIN
    if count == 2:
        widths = [width * 0.54, width * 0.46]
    elif count == 3:
        widths = [width * 0.34, width * 0.33, width * 0.33]
    else:
        widths = [width / count] * count

    # Tabellen ohne Kopfzeile (leere Kopfzellen) ohne graue Leerzeile.
    has_head = any(cell.strip() for cell in headers)
    data = [[Paragraph(inline(cell), style_set["TableHead"]) for cell in headers]] if has_head else []
    for row in rows:
        row = row + [""] * max(0, count - len(row))
        data.append([Paragraph(inline(cell), style_set["Table"]) for cell in row[:count]])

    table = Table(data, colWidths=widths, repeatRows=1 if has_head else 0, hAlign="LEFT")
    table.setStyle(TableStyle(([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAEAEA"))] if has_head else []) + [
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#A0A0A0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def markdown_to_story(markdown: str, page_breaks: bool):
    style_set = styles()
    story = []
    lines = markdown.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index]

        if line.startswith("|") and index + 1 < len(lines) and is_table_separator(lines[index + 1]):
            headers = [cell.strip() for cell in line.strip().strip("|").split("|")]
            index += 2
            rows = []
            while index < len(lines) and lines[index].startswith("|"):
                rows.append([cell.strip() for cell in lines[index].strip().strip("|").split("|")])
                index += 1
            story.extend([Spacer(1, 3), make_table(headers, rows, style_set), Spacer(1, 6)])
            continue

        if line.startswith("# "):
            story.append(Paragraph(inline(line[2:]), style_set["DocTitle"]))
        elif line.startswith("## "):
            heading = line[3:].strip()
            if page_breaks and heading in {"Teil A – Allgemeine Geschäftsbedingungen", "Teil B – Widerrufsbelehrung", "Teil C – Muster-Widerrufsformular"} and story:
                story.append(PageBreak())
            story.append(Paragraph(inline(heading), style_set["H1"]))
        elif line.startswith("### "):
            story.append(Paragraph(inline(line[4:]), style_set["H2"]))
        elif line.startswith("#### "):
            story.append(Paragraph(inline(line[5:]), style_set["H3"]))
        elif line.strip() == "---":
            story.append(Spacer(1, 8))
        elif line.startswith(">"):
            story.append(Paragraph(inline(line.lstrip(">").strip()), style_set["Body"]))
        elif line.startswith("- "):
            story.append(Paragraph("• " + inline(line[2:]), style_set["List"]))
        elif re.match(r"^\d+\. ", line):
            number, text = line.split(". ", 1)
            story.append(Paragraph(f"{number}. {inline(text)}", style_set["List"]))
        elif line.strip():
            story.append(Paragraph(inline(line), style_set["Body"]))
        else:
            story.append(Spacer(1, 2.5))
        index += 1

    return story


def footer(footer_text: str):
    def draw(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D0D0D0"))
        canvas.line(MARGIN, 1.38 * cm, PAGE_WIDTH - MARGIN, 1.38 * cm)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.setFont(SANS, 7.8)
        canvas.drawString(MARGIN, 0.95 * cm, footer_text)
        canvas.drawRightString(PAGE_WIDTH - MARGIN, 0.95 * cm, f"Seite {document.page}")
        canvas.restoreState()
    return draw


def main() -> int:
    parser = argparse.ArgumentParser(description="Markdown in PDF mit statischen Source-Fonts umwandeln.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", "-o", type=Path)
    parser.add_argument("--footer", default=DEFAULT_FOOTER)
    parser.add_argument("--no-footer", action="store_true")
    parser.add_argument("--no-section-page-breaks", action="store_true")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Fehler: Datei nicht gefunden: {args.input}", file=sys.stderr)
        return 1

    try:
        register_fonts()
    except (FileNotFoundError, OSError) as error:
        print(f"Fehler beim Laden der Schriftarten:\n{error}", file=sys.stderr)
        return 1

    output = args.output if args.output else args.input.with_suffix(".pdf")
    output.parent.mkdir(parents=True, exist_ok=True)
    story = markdown_to_story(args.input.read_text(encoding="utf-8"), not args.no_section_page_breaks)

    document = SimpleDocTemplate(str(output), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=1.75 * cm, bottomMargin=1.75 * cm, title=args.input.stem, author="HMNX.Prints")
    if args.no_footer:
        document.build(story)
    else:
        draw_footer = footer(args.footer)
        document.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)

    print(f"PDF erstellt: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
