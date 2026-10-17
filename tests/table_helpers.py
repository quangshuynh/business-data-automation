"""
shared helpers for spreadsheet clean/compare tests
"""

from pathlib import Path

from ordixa_helpers import ROOT, write_rows

from app.ordixa.tabular_profile import validate_table_profile

INVENTORY_DIR = ROOT / "examples" / "ordixa" / "exports" / "inventory"
PROFILES_DIR = ROOT / "examples" / "ordixa" / "profiles"
CLEAN_PROFILE = PROFILES_DIR / "inventory-clean.toml"
COMPARE_PROFILE = PROFILES_DIR / "inventory-compare.toml"

HEADER = ["SKU", "Name", "Price", "Qty", "Counted"]


def table_document(kind="compare", **table):
    """
    builds a small table profile document for edge-case tests
    :param kind: clean or compare
    :param table: overrides for the [table] section
    :returns: mutable profile dictionary
    """
    return {
        "schema_version": 1,
        "workflow": {"kind": kind},
        "profile": {"name": "test-table", "version": "1.0.0"},
        "input": {"formats": ["csv", "xlsx"]},
        "amounts": {"currency": "USD", "currency_symbols": ["$"]},
        "table": {
            "key": ["sku"],
            "blank_values": ["N/A"],
            "date_formats": ["%Y-%m-%d", "%m/%d/%Y"],
            **table,
        },
        "columns": {
            "sku": {"source": "SKU", "type": "identifier", "required": True},
            "name": {"source": "Name", "required": True},
            "price": {"source": "Price", "type": "decimal", "required": True},
            "qty": {"source": "Qty", "type": "integer"},
            "counted": {"source": "Counted", "type": "date"},
        },
    }


def table_profile(kind="compare", mutate=None, **table):
    """
    builds a validated table profile, optionally modified
    :param kind: clean or compare
    :param mutate: optional function that edits the document in place
    :param table: overrides for the [table] section
    :returns: validated table profile
    """
    document = table_document(kind, **table)
    if mutate:
        mutate(document)
    return validate_table_profile(document, source_path="test-table.toml")


def write_table(path, rows, header=None):
    """
    writes a small CSV table using the default test header
    :param path: destination CSV path
    :param rows: list of row cell lists
    :param header: optional header cells
    :returns: destination path
    """
    return write_rows(Path(path), header or HEADER, rows)
