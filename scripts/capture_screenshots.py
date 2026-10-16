"""
regenerates the README and docs screenshots from the real fictional demo

maintainer tool, not part of the product or CI. It needs LibreOffice (set
SOFFICE if soffice is not on PATH or in the default install location) and
PyMuPDF (python -m pip install pymupdf). Every image comes from a real run:

- workbook sheets: the demo run's ordixa_exceptions.xlsx rendered by
  LibreOffice Calc. For width, each capture uses a copy of the workbook in
  which some columns are left out and the page is A3; the remaining cells
  are untouched. Captions in docs/DEMO.md name the hidden columns.
- terminal images: the exact text printed by the inspect and demo commands,
  drawn in a monospace font. Nothing is retyped or edited; the scratch run
  directory is shown as output/demo, the demo's default location.

run from the repository root with: python -m scripts.capture_screenshots
"""

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter

from app.ordixa import demo
from app.ordixa.inspection import DEFAULT_MAX_ROWS, format_report, inspect_path
from app.ordixa.manifest import WORKBOOK_NAME, write_run_outputs
from app.ordixa.pipeline import process
from app.ordixa.profile import load_profile

ROOT = Path(__file__).resolve().parents[1]

IMAGES = ROOT / "docs" / "images"
WIDTH_PX = 1600
FONTS = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
GRAPHITE = (0x11 / 255, 0x1D / 255, 0x22 / 255)
SURFACE = (0x22 / 255, 0x34 / 255, 0x3A / 255)
CHARTREUSE = (0xD9 / 255, 0xF1 / 255, 0x7A / 255)
OFF_WHITE = (0xF2 / 255, 0xF4 / 255, 0xEF / 255)
AMBER = (0xE6 / 255, 0xAE / 255, 0x65 / 255)
MUTED = (0x9F / 255, 0xB0 / 255, 0xAA / 255)
RULE = (0xC9 / 255, 0xD1 / 255, 0xCC / 255)

# sheet name, output file, columns left out of the capture copy, orientation
SHEETS = [
    ("Summary", "workbook-summary.png", "", "portrait"),
    ("Exceptions", "workbook-exceptions.png", "KLMN", "landscape"),
    ("Rejected Rows", "workbook-rejected-rows.png", "K", "landscape"),
    ("Full Ledger", "workbook-full-ledger.png", "BDFGQRSTU", "landscape"),
]


def soffice():
    """
    locates the LibreOffice executable
    :returns: path to soffice
    """
    candidates = [
        os.environ.get("SOFFICE"),
        shutil.which("soffice"),
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    sys.exit("LibreOffice not found; set SOFFICE to the soffice executable")


def font(name, fallback):
    """
    picks an installed font file, or a PyMuPDF base-14 font
    :param name: font file name in the system font folder
    :param fallback: base-14 font name
    :returns: tuple of text-call keyword arguments and a font for measuring
    """
    path = FONTS / name
    if path.exists():
        return {"fontfile": str(path), "fontname": path.stem}, pymupdf.Font(
            fontfile=str(path)
        )
    return {"fontname": fallback}, pymupdf.Font(fallback)


def capture_sheet(workbook_path, sheet_name, omitted, orientation, work_dir, target):
    """
    renders one worksheet through LibreOffice and crops it to its content
    :param workbook_path: generated workbook
    :param sheet_name: sheet to capture
    :param omitted: column letters left out of the capture copy
    :param orientation: page orientation for the capture
    :param work_dir: scratch directory
    :param target: output PNG path
    :returns: none
    """
    workbook = load_workbook(workbook_path)
    for other in list(workbook.sheetnames):
        if other != sheet_name:
            del workbook[other]
    sheet = workbook[sheet_name]
    # omitted columns are deleted rather than hidden: LibreOffice misplaces
    # indented figures next to blank cells when columns are hidden
    kept = [
        get_column_letter(index)
        for index in range(1, sheet.max_column + 1)
        if get_column_letter(index) not in omitted
    ]
    widths = [sheet.column_dimensions[letter].width for letter in kept]
    for letter in sorted(omitted, key=column_index_from_string, reverse=True):
        sheet.delete_cols(column_index_from_string(letter))
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.auto_filter.ref = None
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
    sheet.page_setup.orientation = orientation
    sheet.oddFooter.left.text = sheet.oddFooter.right.text = None
    copy = work_dir / f"{target.stem}.xlsx"
    workbook.save(copy)

    subprocess.run(
        [soffice(), "--headless", "--convert-to", "pdf", "--outdir", str(work_dir)]
        + [str(copy)],
        check=True,
        capture_output=True,
    )
    with pymupdf.open(work_dir / f"{target.stem}.pdf") as document:
        crop_page(document[0], target)


def crop_page(page, target):
    """
    crops a rendered page to its content with a hairline frame
    :param page: PDF page
    :param target: output PNG path
    :returns: none
    """
    boxes = [pymupdf.Rect(block[:4]) for block in page.get_text("blocks")]
    boxes += [drawing["rect"] for drawing in page.get_drawings()]
    content = boxes[0]
    for box in boxes[1:]:
        content |= box
    clip = content + (-14, -14, 14, 14)
    page.draw_rect(clip, color=RULE, width=0.8)
    zoom = WIDTH_PX / clip.width
    page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip).save(target)


def render_terminal(command, output, target, highlight):
    """
    draws captured command output as a dark terminal panel
    :param command: command line shown on the first line
    :param output: text the command printed
    :param target: output PNG path
    :param highlight: function returning a color for a line, or None
    :returns: none
    """
    mono, measure = font("consola.ttf", "cour")
    lines = output.rstrip("\n").splitlines()
    columns = max(len(line) for line in lines + [command]) + 4
    size = 11
    char = measure.text_length("0", size)
    line_height = size * 1.45
    width = columns * char + 40
    height = (len(lines) + 3) * line_height + 40

    document = pymupdf.open()
    page = document.new_page(width=width, height=height)
    page.draw_rect(page.rect, color=None, fill=GRAPHITE)
    page.draw_rect(pymupdf.Rect(0, 0, width, 4), color=None, fill=CHARTREUSE)
    y = 20 + line_height
    page.insert_text((20, y), "$ ", fontsize=size, color=CHARTREUSE, **mono)
    page.insert_text(
        (20 + 2 * char, y), command, fontsize=size, color=OFF_WHITE, **mono
    )
    y += line_height * 1.5
    for line in lines:
        page.insert_text(
            (20, y), line, fontsize=size, color=highlight(line) or OFF_WHITE, **mono
        )
        y += line_height
    zoom = WIDTH_PX / width
    page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).save(target)
    document.close()


def inspect_colors(line):
    """
    colors inspection lines by kind
    :param line: output line
    :returns: color or None
    """
    text = line.strip()
    if text.startswith("suggestion:"):
        return CHARTREUSE
    if text.startswith(("note:", "warning")):
        return AMBER
    if text.startswith("Everything below"):
        return MUTED
    return None


def demo_colors(line):
    """
    colors demo walkthrough lines by kind
    :param line: output line
    :returns: color or None
    """
    text = line.strip()
    if text.startswith("[") or text.startswith("Demo complete"):
        return CHARTREUSE
    if text.startswith("ok "):
        return (0xB9 / 255, 0xE3 / 255, 0xC6 / 255)
    if set(text) == {"-"}:
        return SURFACE
    if text.startswith("FAIL"):
        return AMBER
    return None


def main():
    """
    regenerates every screenshot
    :returns: none
    """
    IMAGES.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as scratch:
        work_dir = Path(scratch)
        profile = load_profile(demo.DEMO_PROFILE)
        run_dir, _ = write_run_outputs(process(profile, demo.DEMO_INPUT), work_dir)
        for sheet_name, file_name, omitted, orientation in SHEETS:
            capture_sheet(
                run_dir / WORKBOOK_NAME,
                sheet_name,
                omitted,
                orientation,
                work_dir,
                IMAGES / file_name,
            )
            print(f"wrote docs/images/{file_name}")

        report = format_report(inspect_path(demo.DEMO_INPUT), DEFAULT_MAX_ROWS)
        render_terminal(
            "python -m app.ordixa inspect --input examples/ordixa/exports/demo",
            report,
            IMAGES / "cli-inspect.png",
            inspect_colors,
        )
        print("wrote docs/images/cli-inspect.png")

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            demo.main(["--out", str(work_dir / "demo"), "--skip-inspect"])
        output = buffer.getvalue().replace(str(work_dir / "demo"), "output/demo")
        output = output.replace("\\", "/")
        render_terminal(
            "python -m app.ordixa.demo --skip-inspect",
            output,
            IMAGES / "cli-demo-run.png",
            demo_colors,
        )
        print("wrote docs/images/cli-demo-run.png")


if __name__ == "__main__":
    main()
