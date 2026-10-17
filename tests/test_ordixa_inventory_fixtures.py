"""
golden tests for the fictional Saltmarsh Mercantile inventory exports

expected values are typed in from the seeded changes documented in
examples/ordixa/README.md, not produced by the code under test
"""

import csv
from decimal import Decimal

from table_helpers import CLEAN_PROFILE, COMPARE_PROFILE, INVENTORY_DIR

from app.ordixa.tabular import clean_table, compare_tables, key_text
from app.ordixa.tabular_profile import load_table_profile

BEFORE = INVENTORY_DIR / "inventory-before.csv"
AFTER = INVENTORY_DIR / "inventory-after.csv"

ADDED = ["000138", "000139", "BRM-016", "SKU-0091", "SKU-0092", "SKU-0093"]
REMOVED = ["000129", "BRM-011", "SKU-0013", "SKU-0058"]
PRICE_CHANGES = {
    "000125": ("22.96", "23.26"),
    "BRM-003": ("2.88", "3.38"),
    "BRM-008": ("3.18", "2.93"),
    "SKU-0004": ("88.51", "89.51"),
    "SKU-0010": ("20.27", "17.77"),
    "SKU-0021": ("54.12", "54.87"),
    "SKU-0035": ("80.63", "85.63"),
    "SKU-0050": ("68.20", "68.19"),
}
STOCK_CHANGES = {
    "000131": (16, 40),
    "000134": (52, 46),
    "BRM-005": (33, 48),
    "SKU-0002": (8, 5),
    "SKU-0004": (16, 26),
    "SKU-0017": (17, 12),
    "SKU-0029": (21, 33),
    "SKU-0044": (62, 61),
    "SKU-0061": (77, 97),
    "SKU-0077": (52, 45),
}
OTHER_CHANGES = {
    ("SKU-0066", "category"): ("Hardware", "Outdoor"),
    ("SKU-0083", "product_name"): ("Coastal Enamel Mug", "Coastal Enamel mug"),
}
AMBIGUOUS = ["SKU-0070"]
INVALID = ["SKU-0025", "SKU-0048"]
# formatting-only edits in the later export that must stay unchanged
FORMATTING_ONLY = ["SKU-0009", "SKU-0028", "SKU-0030", "SKU-0055", "000123"]


def source_rows(path):
    """
    reads a fixture export without Ordixa
    :param path: CSV path
    :returns: list of dictionaries
    """
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_fixture_shape_is_as_documented():
    """
    tests the raw fixtures independently of the cleaning code
    :returns: none
    """
    before = source_rows(BEFORE)
    after = source_rows(AFTER)
    assert (len(before), len(after)) == (121, 124)
    before_skus = {row["Item SKU"].strip() for row in before}
    after_skus = {row["Item SKU"].strip() for row in after} - {""}
    assert len(before_skus) == 120
    assert sorted(after_skus - before_skus) == ADDED
    assert sorted(before_skus - after_skus) == REMOVED
    assert list(source_rows(AFTER)[0])[:2] == ["Product Name", "Item SKU"]


def test_cleaning_the_inventory_exports():
    """
    tests cleaning totals for both weekly exports
    :returns: none
    """
    profile = load_table_profile(CLEAN_PROFILE, "clean")
    before = clean_table(profile, BEFORE).counts()
    assert (before["rows_read"], before["rows_written"]) == (121, 120)
    assert (before["duplicate_rows_removed"], before["rows_rejected"]) == (1, 0)
    assert before["blank_tokens_normalized"] == 3

    after = clean_table(profile, AFTER)
    counts = after.counts()
    assert (counts["rows_read"], counts["rows_written"]) == (124, 119)
    assert counts["rows_rejected"] == 5
    assert sorted((i.row, i.code) for i in after.issues if i.row) == [
        (36, "missing_value"),
        (59, "missing_value"),
        (79, "missing_value"),
        (119, "conflicting_key"),
        (122, "conflicting_key"),
    ]


def test_comparing_the_inventory_exports():
    """
    tests every comparison category against the hand-entered expectations
    :returns: none
    """
    profile = load_table_profile(COMPARE_PROFILE, "compare")
    result = compare_tables(profile, BEFORE, AFTER)

    def keys(kind):
        return sorted(key_text(key) for key in result.keys_with(kind))

    assert keys("added") == ADDED
    assert keys("removed") == REMOVED
    assert keys("ambiguous") == AMBIGUOUS
    assert keys("invalid") == INVALID

    modified = set(PRICE_CHANGES) | set(STOCK_CHANGES) | {k for k, _ in OTHER_CHANGES}
    assert keys("modified") == sorted(modified)
    assert len(modified) == 19
    for sku in FORMATTING_ONLY:
        assert result.status[(sku,)] == "unchanged", sku

    expected = {
        (sku, "unit_price"): (Decimal(old), Decimal(new))
        for sku, (old, new) in PRICE_CHANGES.items()
    }
    expected |= {(sku, "quantity_on_hand"): pair for sku, pair in STOCK_CHANGES.items()}
    expected |= OTHER_CHANGES
    found = {(key_text(c.key), c.column): (c.before, c.after) for c in result.changes}
    assert found == expected

    counts = result.counts()
    universe = 120 + len(ADDED)
    unchanged = (
        universe - len(ADDED) - len(REMOVED) - 19 - len(AMBIGUOUS) - len(INVALID)
    )
    assert counts["unchanged"] == unchanged == 94
    assert counts["unkeyed_rejected_rows"] == 1
    assert counts["changed_values"] == 20
