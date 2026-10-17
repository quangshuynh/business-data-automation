"""
tests for keyed comparison of two table versions
"""

import random
from decimal import Decimal

from openpyxl import Workbook
from table_helpers import HEADER, table_profile, write_table

from app.ordixa.tabular import (
    ADDED,
    AMBIGUOUS,
    INVALID,
    MODIFIED,
    REMOVED,
    UNCHANGED,
    compare_tables,
    key_text,
)

BASE = [
    ["SKU-1", "Mug", "12.00", "10", "2026-10-05"],
    ["SKU-2", "Bowl", "8.50", "4", "2026-10-05"],
    ["SKU-3", "Plate", "15.00", "0", "2026-10-05"],
]


def compare_rows(
    tmp_path, before, after, header_before=None, header_after=None, **args
):
    """
    writes two CSV versions and compares them
    :param tmp_path: pytest temporary directory
    :param before: earlier rows
    :param after: later rows
    :param header_before: optional header for the earlier file
    :param header_after: optional header for the later file
    :param args: arguments for table_profile
    :returns: compare result
    """
    old = write_table(tmp_path / "before.csv", before, header_before)
    new = write_table(tmp_path / "after.csv", after, header_after)
    return compare_tables(table_profile(**args), old, new)


def statuses(result):
    """
    maps display keys to change categories
    :param result: compare result
    :returns: dictionary
    """
    return {key_text(key): kind for key, kind in result.status.items()}


def changes(result):
    """
    lists value changes as canonical text tuples
    :param result: compare result
    :returns: list of tuples
    """
    return [
        (key_text(c.key), c.column, c.before, c.after, c.difference)
        for c in result.changes
    ]


def test_added_removed_modified_and_unchanged(tmp_path):
    """
    tests the four basic change categories
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    after = [
        ["SKU-1", "Mug", "12.00", "10", "2026-10-05"],
        ["SKU-2", "Bowl", "9.00", "4", "2026-10-05"],
        ["SKU-4", "Jug", "20.00", "6", "2026-10-05"],
    ]
    result = compare_rows(tmp_path, BASE, after)
    assert statuses(result) == {
        "SKU-1": UNCHANGED,
        "SKU-2": MODIFIED,
        "SKU-3": REMOVED,
        "SKU-4": ADDED,
    }
    assert changes(result) == [
        ("SKU-2", "price", Decimal("8.50"), Decimal("9.00"), Decimal("0.50"))
    ]
    assert [r.values["sku"] for r in result.added] == ["SKU-4"]
    assert [r.values["sku"] for r in result.removed] == ["SKU-3"]
    counts = result.counts()
    assert (counts["added"], counts["removed"]) == (1, 1)
    assert (counts["modified"], counts["unchanged"]) == (1, 1)


def test_price_and_quantity_changes_are_exact(tmp_path):
    """
    tests one-cent price changes and signed quantity changes
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    after = [
        ["SKU-1", "Mug", "12.01", "10", "2026-10-05"],
        ["SKU-2", "Bowl", "8.50", "1", "2026-10-05"],
        ["SKU-3", "Plate", "15.00", "-2", "2026-10-05"],
    ]
    result = compare_rows(tmp_path, BASE, after)
    assert changes(result) == [
        ("SKU-1", "price", Decimal("12.00"), Decimal("12.01"), Decimal("0.01")),
        ("SKU-2", "qty", 4, 1, -3),
        ("SKU-3", "qty", 0, -2, -2),
    ]
    assert result.counts()["changed_values_by_column"] == {"price": 1, "qty": 2}


def test_formatting_differences_are_not_changes(tmp_path):
    """
    tests that configured normalization makes formatting-only edits equal:
    currency symbols, trailing zeros, padding, date formats, and blank tokens
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    after = [
        [" SKU-1", "Mug ", "$12", " 10", "10/05/2026"],
        ["SKU-2", "Bowl", "8.5", "4", "2026-10-05"],
        ["SKU-3", "Plate", "15.00", "0", "2026-10-05"],
    ]
    result = compare_rows(tmp_path, BASE, after)
    assert set(statuses(result).values()) == {UNCHANGED}


def test_meaningful_text_changes_are_kept(tmp_path):
    """
    tests that case, punctuation, inner spacing, and accents are changes
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    before = [
        ["SKU-1", "Enamel Mug", "1", "", ""],
        ["SKU-2", "Café", "1", "", ""],
        ["SKU-3", "Tea  Towel", "1", "", ""],
    ]
    after = [
        ["SKU-1", "Enamel mug", "1", "", ""],
        ["SKU-2", "Cafe", "1", "", ""],
        ["SKU-3", "Tea Towel", "1", "", ""],
    ]
    result = compare_rows(tmp_path, before, after)
    assert [c[:4] for c in changes(result)] == [
        ("SKU-1", "name", "Enamel Mug", "Enamel mug"),
        ("SKU-2", "name", "Café", "Cafe"),
        ("SKU-3", "name", "Tea  Towel", "Tea Towel"),
    ]

    def collapse(document):
        document["columns"]["name"]["whitespace"] = "collapse"

    collapsed = compare_rows(tmp_path, before, after, mutate=collapse)
    assert statuses(collapsed)["SKU-3"] == UNCHANGED


def test_reordered_rows_and_columns_give_the_same_result(tmp_path):
    """
    tests that records match by key, never by row or column position
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    after = [
        ["SKU-1", "Mug", "13.00", "10", "2026-10-05"],
        ["SKU-2", "Bowl", "8.50", "4", "2026-10-05"],
        ["SKU-4", "Jug", "20.00", "6", "2026-10-05"],
    ]
    straight = compare_rows(tmp_path / "a", BASE, after)

    order = [4, 2, 0, 3, 1]
    header = [HEADER[i] for i in order]
    shuffled = [[row[i] for i in order] for row in reversed(after)]
    moved = compare_rows(
        tmp_path / "b", list(reversed(BASE)), shuffled, header_after=header
    )

    assert statuses(moved) == statuses(straight)
    assert changes(moved) == changes(straight)


def test_exact_duplicates_do_not_make_a_key_ambiguous(tmp_path):
    """
    tests that an exact duplicate is reported but still compared once
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    after = BASE + [["SKU-2", "Bowl", "$8.50", "4", "2026-10-05"]]
    result = compare_rows(tmp_path, BASE, after)
    assert statuses(result)["SKU-2"] == UNCHANGED
    assert [i.code for i in result.issues] == ["duplicate_row"]
    assert result.issues[0].side == "after"


def test_conflicting_keys_are_ambiguous_and_never_resolved(tmp_path):
    """
    tests that a key with two different rows is neither added, removed, nor
    modified, on either side
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    before = BASE + [
        ["SKU-9", "Vase", "30.00", "1", ""],
        ["SKU-9", "Vase", "31.00", "1", ""],
    ]
    after = [
        ["SKU-1", "Mug", "12.00", "10", "2026-10-05"],
        ["SKU-1", "Mug", "12.00", "11", "2026-10-05"],
        BASE[1],
        BASE[2],
    ]
    result = compare_rows(tmp_path, before, after)
    assert statuses(result) == {
        "SKU-1": AMBIGUOUS,
        "SKU-2": UNCHANGED,
        "SKU-3": UNCHANGED,
        "SKU-9": AMBIGUOUS,
    }
    assert result.added == [] and result.removed == [] and result.changes == []
    assert result.counts()["ambiguous_keys"] == 2
    assert [(i.side, i.code) for i in result.issues] == [
        ("before", "conflicting_key"),
        ("before", "conflicting_key"),
        ("after", "conflicting_key"),
        ("after", "conflicting_key"),
    ]


def test_rejected_rows_make_their_key_invalid_not_removed(tmp_path):
    """
    tests that a product whose later row is rejected is not reported as
    removed, and a rejected new row is not reported as added
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    after = [
        ["SKU-1", "Mug", "", "10", "2026-10-05"],
        BASE[1],
        BASE[2],
        ["SKU-5", "Cup", "abc", "1", ""],
        ["", "Unlabeled", "3.00", "1", ""],
    ]
    result = compare_rows(tmp_path, BASE, after)
    assert statuses(result) == {
        "SKU-1": INVALID,
        "SKU-2": UNCHANGED,
        "SKU-3": UNCHANGED,
        "SKU-5": INVALID,
    }
    counts = result.counts()
    assert (counts["invalid_keys"], counts["unkeyed_rejected_rows"]) == (2, 1)
    assert (counts["added"], counts["removed"]) == (0, 0)


def test_compound_keys(tmp_path):
    """
    tests that a compound key keeps the same SKU in two stores apart
    :param tmp_path: pytest temporary directory
    :returns: none
    """

    def add_store(document):
        document["columns"] = {
            "store": {"source": "Store", "type": "identifier"},
            **document["columns"],
        }

    header = ["Store", *HEADER]
    before = [["NORTH", *BASE[0]], ["SOUTH", *BASE[0]]]
    after = [["NORTH", *BASE[0]], ["SOUTH", "SKU-1", "Mug", "11.00", "10", ""]]
    result = compare_rows(
        tmp_path, before, after, header, header, mutate=add_store, key=["store", "sku"]
    )
    assert statuses(result) == {"NORTH / SKU-1": UNCHANGED, "SOUTH / SKU-1": MODIFIED}
    assert changes(result)[0][:2] == ("SOUTH / SKU-1", "price")


def test_leading_zero_identifiers_are_different_records(tmp_path):
    """
    tests that 000123 and 123 are never treated as the same product
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    before = [["000123", "Oats", "4.00", "1", ""]]
    after = [["123", "Oats", "4.00", "1", ""]]
    result = compare_rows(tmp_path, before, after)
    assert statuses(result) == {"000123": REMOVED, "123": ADDED}


def test_null_and_empty_follow_configured_rules(tmp_path):
    """
    tests blank handling: configured tokens equal an empty cell, an
    unconfigured token is a real value, and an XLSX empty cell equals an
    empty CSV cell
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    before = [["SKU-1", "Mug", "1", "N/A", ""], ["SKU-2", "Bowl", "1", "", ""]]
    after = [["SKU-1", "Mug", "1", "", ""], ["SKU-2", "Bowl", "1", "", ""]]
    assert set(statuses(compare_rows(tmp_path, before, after)).values()) == {UNCHANGED}

    # without N/A configured, the quantity N/A is not a whole number
    strict = compare_rows(tmp_path, before, after, blank_values=[])
    assert statuses(strict)["SKU-1"] == INVALID

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADER)
    sheet.append(["SKU-1", "Mug", 1, None, None])
    sheet.append(["SKU-2", "Bowl", 1, None, None])
    workbook.save(tmp_path / "after.xlsx")
    mixed = compare_tables(
        table_profile(), tmp_path / "before.csv", tmp_path / "after.xlsx"
    )
    assert set(statuses(mixed).values()) == {UNCHANGED}


def test_text_blank_tokens_are_values_unless_configured(tmp_path):
    """
    tests that a text column holding a token differs from blank unless the
    token is configured
    :param tmp_path: pytest temporary directory
    :returns: none
    """

    def add_note(document):
        document["columns"]["note"] = {"source": "Note"}

    header = [*HEADER, "Note"]
    before = [["SKU-1", "Mug", "1", "", "", "-"]]
    after = [["SKU-1", "Mug", "1", "", "", ""]]
    result = compare_rows(tmp_path, before, after, header, header, mutate=add_note)
    assert changes(result) == [("SKU-1", "note", "-", None, None)]
    configured = compare_rows(
        tmp_path, before, after, header, header, mutate=add_note, blank_values=["-"]
    )
    assert statuses(configured)["SKU-1"] == UNCHANGED


def test_dates_compare_by_calendar_day(tmp_path):
    """
    tests that dates in different declared formats compare by value
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    after = [
        ["SKU-1", "Mug", "12.00", "10", "10/05/2026"],
        ["SKU-2", "Bowl", "8.50", "4", "10/06/2026"],
        BASE[2],
    ]
    result = compare_rows(tmp_path, BASE, after)
    assert [c[:2] for c in changes(result)] == [("SKU-2", "counted")]


def test_ignored_and_missing_columns_are_not_compared(tmp_path):
    """
    tests compare.ignore, and that a column absent from one file is noted
    instead of turning every record into a change
    :param tmp_path: pytest temporary directory
    :returns: none
    """

    def ignore_counted(document):
        document["compare"] = {"ignore": ["counted"]}

    after = [row[:4] for row in BASE]
    after[0][3] = "11"
    result = compare_rows(
        tmp_path, BASE, after, header_after=HEADER[:4], mutate=ignore_counted
    )
    assert result.compared_columns == ["name", "price", "qty"]
    assert [c[:2] for c in changes(result)] == [("SKU-1", "qty")]
    assert not [i for i in result.issues if i.code == "column_not_compared"]

    unignored = compare_rows(tmp_path, BASE, after, header_after=HEADER[:4])
    assert unignored.compared_columns == ["name", "price", "qty"]
    assert [i.column for i in unignored.issues if i.code == "column_not_compared"] == [
        "counted"
    ]


def test_keys_are_ordered_naturally(tmp_path):
    """
    tests natural key order so SKU-9 sorts before SKU-10
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    rows = [[f"SKU-{n}", "Mug", "1", "", ""] for n in (10, 9, 100, 1)]
    result = compare_rows(tmp_path, [], rows)
    assert [key_text(k) for k in result.status] == [
        "SKU-1",
        "SKU-9",
        "SKU-10",
        "SKU-100",
    ]


def test_large_comparison_uses_indexed_keys(tmp_path):
    """
    tests a 20,000-row comparison with seeded changes found exactly
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    rng = random.Random(7)
    before = [
        [f"SKU-{n:06d}", f"Item {n}", f"{rng.randrange(100, 99999) / 100:.2f}", "5", ""]
        for n in range(20_000)
    ]
    after = [list(row) for row in before[100:]]
    for row in after[::500]:
        row[3] = "6"
    after.extend([f"NEW-{n}", "New", "1.00", "1", ""] for n in range(50))
    rng.shuffle(after)

    counts = compare_rows(tmp_path, before, after).counts()
    assert counts["removed"] == 100
    assert counts["added"] == 50
    assert counts["modified"] == len(range(0, 19_900, 500))
    assert counts["unchanged"] == 19_900 - counts["modified"]
