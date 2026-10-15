"""
shared helpers for Ordixa tests
"""

import csv
import shutil
import tomllib
from pathlib import Path

from openpyxl import Workbook

from app.ordixa.profile import validate_profile_document

ROOT = Path(__file__).resolve().parents[1]
EXPORTS_DIR = ROOT / "examples" / "ordixa" / "exports"
PROFILE_PATH = ROOT / "examples" / "ordixa" / "profiles" / "harbor-lane.toml"


def profile_document():
    """
    reads the example profile as a mutable dictionary
    :returns: parsed TOML document
    """
    with PROFILE_PATH.open("rb") as handle:
        return tomllib.load(handle)


def build_profile(mutate=None):
    """
    builds a validated profile from the example, optionally modified
    :param mutate: optional function that edits the document in place
    :returns: validated profile
    """
    document = profile_document()
    if mutate:
        mutate(document)
    return validate_profile_document(document, source_path=PROFILE_PATH)


def copy_exports(fixture_set, destination, names=None):
    """
    copies fixture exports into a scratch input directory
    :param fixture_set: clean or problematic
    :param destination: target directory
    :param names: optional subset of file names
    :returns: destination path
    """
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for path in sorted((EXPORTS_DIR / fixture_set).glob("*.csv")):
        if names is None or path.name in names:
            shutil.copy(path, destination / path.name)
    return destination


def csv_to_xlsx(csv_path, xlsx_path, sheet_title="Export"):
    """
    converts a fixture CSV into an XLSX workbook with text cells
    :param csv_path: source CSV path
    :param xlsx_path: target workbook path
    :param sheet_title: worksheet name
    :returns: target path
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_title
    with Path(csv_path).open(newline="", encoding="utf-8") as handle:
        for row in csv.reader(handle):
            sheet.append(row)
    workbook.save(xlsx_path)
    return Path(xlsx_path)
