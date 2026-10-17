"""
tests for deterministic table cleaning
"""

import hashlib
from datetime import date
from decimal import Decimal

import pytest
from openpyxl import Workbook
from ordixa_helpers import write_rows
from table_helpers import HEADER, table_profile, write_table

from app.ordixa.issues import InputError
from app.ordixa.tabular import (
    DUPLICATE_REMOVED,
    NOTE,
    REJECTED,
    as_text,
    clean_table,
)


def clean_rows(tmp_path, rows, header=None, **profile_args):
    """
    cleans a small CSV and returns the result
    :param tmp_path: pytest temporary directory
    :param rows: row cell lists
    :param header: optional header
    :param profile_args: arguments for table_profile
    :returns: clean result
    """
    profile_args.setdefault("kind", "clean")
    path = write_table(tmp_path / "items.csv", rows, header)
    return clean_table(table_profile(**profile_args), path)


def cleaned(result):
    """
    gives cleaned records as canonical text keyed by column
    :param result: clean result
    :returns: list of dictionaries
    """
    return [
        {name: as_text(value) for name, value in record.values.items()}
        for record in result.records
    ]


def codes(result, outcome=None):
    """
    lists issue codes, optionally for one outcome
    :param result: clean result
    :param outcome: outcome label to filter by
    :returns: list of (row, code) pairs
    """
    return [
        (issue.row, issue.code)
        for issue in result.issues
        if outcome is None or issue.outcome == outcome
    ]


def test_whitespace_is_trimmed_but_inner_spaces_kept(tmp_path):
    """
    tests trimming, and that inner spaces collapse only when configured
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    rows = [[" SKU-1 ", "  Brass  Hinge ", " 4.50 ", " 7", "2026-10-05 "]]
    result = clean_rows(tmp_path, rows)
    assert cleaned(result) == [
        {
            "sku": "SKU-1",
            "name": "Brass  Hinge",
            "price": "4.50",
            "qty": "7",
            "counted": "2026-10-05",
        }
    ]
    assert result.stats["whitespace_normalized"] == 5

    def collapse(document):
        document["columns"]["name"]["whitespace"] = "collapse"

    collapsed = clean_rows(tmp_path, rows, mutate=collapse)
    assert cleaned(collapsed)[0]["name"] == "Brass Hinge"


def test_names_are_never_recased(tmp_path):
    """
    tests that names keep their exact capitalization
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    result = clean_rows(tmp_path, [["SKU-1", "mcKINLEY ave. Mug", "1", "", ""]])
    assert cleaned(result)[0]["name"] == "mcKINLEY ave. Mug"


def test_blank_tokens_are_exact_and_configured(tmp_path):
    """
    tests that only the configured blank tokens become blank
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    rows = [["SKU-1", "Mug", "1", "N/A", ""], ["SKU-2", "NA", "1", "", "N/A"]]
    result = clean_rows(tmp_path, rows)
    assert [r["qty"] for r in cleaned(result)] == ["", ""]
    # "NA" is not a configured token, so the name keeps it
    assert cleaned(result)[1]["name"] == "NA"
    assert result.stats["blank_tokens_normalized"] == 2


def test_columns_are_renamed_and_ordered_by_the_profile(tmp_path):
    """
    tests explicit mapping: output names and order come from the profile,
    regardless of source column order, and unmapped columns are dropped
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    header = ["Counted", "Notes", "Qty", "Price", "Name", "SKU"]
    rows = [["2026-10-05", "call supplier", "3", "1.00", "Mug", "SKU-1"]]
    result = clean_rows(tmp_path, rows, header)

    assert list(result.records[0].values) == ["sku", "name", "price", "qty", "counted"]
    assert result.unmapped_columns == ["Notes"]
    note = [i for i in result.issues if i.code == "unmapped_columns"][0]
    assert note.outcome == NOTE and "Notes" in note.message
    assert "call supplier" not in repr(result.issues)


def test_missing_required_columns_are_reported_together(tmp_path):
    """
    tests that every missing required column is named, with a close match
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    path = write_rows(tmp_path / "items.csv", ["SKU", "Prices"], [["SKU-1", "1"]])
    with pytest.raises(InputError) as caught:
        clean_table(table_profile("clean"), path)
    message = str(caught.value)
    assert "'Price' (found 'Prices')" in message
    assert "'Name'" in message and "'SKU'" not in message


def test_missing_optional_columns_are_noted(tmp_path):
    """
    tests that an absent optional column is blank and noted, not an error
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    header = ["SKU", "Name", "Price"]
    result = clean_rows(tmp_path, [["SKU-1", "Mug", "1"]], header)
    assert result.missing_columns == ["qty", "counted"]
    assert cleaned(result)[0]["qty"] == ""
    assert codes(result, NOTE).count((0, "optional_column_missing")) == 2


def test_required_values_reject_the_row(tmp_path):
    """
    tests that a blank required value rejects the row and names the column
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    rows = [["SKU-1", "Mug", "", "1", ""], ["SKU-2", "N/A", "2.00", "1", ""]]
    result = clean_rows(tmp_path, rows)
    assert result.records == []
    issues = [(i.row, i.code, i.column, i.key) for i in result.issues]
    assert issues == [
        (2, "missing_value", "price", "SKU-1"),
        (3, "missing_value", "name", "SKU-2"),
    ]


def test_exact_duplicates_are_removed_after_normalization(tmp_path):
    """
    tests that rows identical after trimming and typing collapse to the first
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    rows = [
        ["SKU-1", "Mug", "24.00", "3", "2026-10-05"],
        ["SKU-1 ", "Mug", "$24", "3", "10/05/2026"],
        ["SKU-2", "Bowl", "5.00", "1", ""],
    ]
    result = clean_rows(tmp_path, rows)
    assert [r["sku"] for r in cleaned(result)] == ["SKU-1", "SKU-2"]
    assert codes(result, DUPLICATE_REMOVED) == [(3, "duplicate_row")]
    assert result.counts()["duplicate_keys"] == 1
    assert result.counts()["conflicting_keys"] == 0


def test_conflicting_keys_hold_back_every_copy(tmp_path):
    """
    tests that rows sharing a key with different values are never merged and
    no copy is chosen; the message names columns, never values
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    rows = [
        ["SKU-1", "Mug", "24.00", "3", ""],
        ["SKU-2", "Bowl", "5.00", "1", ""],
        ["SKU-1", "Mug", "26.50", "3", ""],
    ]
    result = clean_rows(tmp_path, rows)
    assert [r["sku"] for r in cleaned(result)] == ["SKU-2"]
    assert codes(result, REJECTED) == [(2, "conflicting_key"), (4, "conflicting_key")]
    assert result.conflicting_keys == {("SKU-1",)}
    message = result.issues[0].message
    assert "price" in message and "26.50" not in message and "24.00" not in message


def test_a_key_shared_with_a_rejected_row_is_held_back(tmp_path):
    """
    tests that a valid row is not silently preferred over a rejected copy
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    rows = [["SKU-1", "Mug", "24.00", "3", ""], ["SKU-1", "Mug", "", "3", ""]]
    result = clean_rows(tmp_path, rows)
    assert result.records == []
    assert codes(result, REJECTED) == [(2, "key_on_rejected_row"), (3, "missing_value")]


def test_leading_zeros_and_text_identifiers_are_preserved(tmp_path):
    """
    tests that identifiers keep leading zeros, case, and separators
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    rows = [
        ["000123", "Oats", "1", "", ""],
        ["SKU-0042", "Mug", "1", "", ""],
        ["ABC-009", "Seeds", "1", "", ""],
        ["abc-009", "Seeds", "1", "", ""],
    ]
    result = clean_rows(tmp_path, rows)
    assert [r["sku"] for r in cleaned(result)] == [
        "000123",
        "SKU-0042",
        "ABC-009",
        "abc-009",
    ]
    assert result.conflicting_keys == set()


def test_invalid_identifiers_are_rejected_without_echoing_them(tmp_path):
    """
    tests that formula-like or spaced identifiers are rejected and that the
    value appears only in the separate value field
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    rows = [["=HYPERLINK(1)", "Mug", "1", "", ""], ["SKU 1", "Mug", "1", "", ""]]
    result = clean_rows(tmp_path, rows)
    assert codes(result) == [(2, "invalid_identifier"), (3, "invalid_identifier")]
    assert result.issues[0].value == "=HYPERLINK(1)"
    assert all("HYPERLINK" not in issue.message for issue in result.issues)
    assert result.unkeyed_rejections == 2


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1,249.50", "1249.50"),
        ("$0.10", "0.10"),
        ("12.5", "12.50"),
        ("-3.00", "-3.00"),
        ("9999999999.99", "9999999999.99"),
    ],
)
def test_decimal_amounts_are_exact(tmp_path, text, expected):
    """
    tests exact decimal parsing using the profile's declared separators
    :param tmp_path: pytest temporary directory
    :param text: source amount
    :param expected: canonical text
    :returns: none
    """
    result = clean_rows(tmp_path, [["SKU-1", "Mug", text, "", ""]])
    value = result.records[0].values["price"]
    assert isinstance(value, Decimal)
    assert as_text(value) == expected


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("12.345", "too_many_decimal_places"),
        ("12,50", "invalid_amount"),
        ("1.249,50", "invalid_amount"),
        ("(4.00)", "invalid_amount"),
        ("4.00 EUR", "invalid_amount"),
        ("NaN", "invalid_amount"),
        ("10000000000.00", "amount_out_of_range"),
    ],
)
def test_ambiguous_amounts_are_rejected_not_rounded(tmp_path, text, code):
    """
    tests that amounts are never rounded or guessed
    :param tmp_path: pytest temporary directory
    :param text: source amount
    :param code: expected issue code
    :returns: none
    """
    result = clean_rows(tmp_path, [["SKU-1", "Mug", text, "", ""]])
    assert result.records == []
    assert codes(result) == [(2, code)]


def test_integers_and_dates_follow_declared_rules(tmp_path):
    """
    tests whole-number quantities and declared date formats
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    rows = [
        ["SKU-1", "Mug", "1", "007", "10/05/2026"],
        ["SKU-2", "Mug", "1", "-2", "2026-10-05"],
        ["SKU-3", "Mug", "1", "3.5", ""],
        ["SKU-4", "Mug", "1", "1,000", ""],
        ["SKU-5", "Mug", "1", "", "2026-02-30"],
        ["SKU-6", "Mug", "1", "", "05.10.2026"],
    ]
    result = clean_rows(tmp_path, rows)
    assert [(r["qty"], r["counted"]) for r in cleaned(result)] == [
        ("7", "2026-10-05"),
        ("-2", "2026-10-05"),
    ]
    assert result.records[0].values["counted"] == date(2026, 10, 5)
    assert codes(result) == [
        (4, "invalid_integer"),
        (5, "invalid_integer"),
        (6, "invalid_calendar_date"),
        (7, "invalid_date"),
    ]


def test_dates_matching_two_declared_formats_are_ambiguous(tmp_path):
    """
    tests that a date readable two ways is rejected rather than guessed
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    rows = [
        ["SKU-1", "Mug", "1", "", "03/04/2026"],
        ["SKU-2", "Mug", "1", "", "13/04/2026"],
    ]
    result = clean_rows(tmp_path, rows, date_formats=["%m/%d/%Y", "%d/%m/%Y"])
    assert codes(result) == [(2, "ambiguous_date")]
    assert cleaned(result)[0]["counted"] == "2026-04-13"


def test_unicode_text_is_kept_exactly(tmp_path):
    """
    tests that accented and non-Latin text passes through unchanged
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    names = ["Café Crème Mug", "Ørsted Bowl", "茶碗"]
    rows = [[f"SKU-{i}", name, "1", "", ""] for i, name in enumerate(names)]
    result = clean_rows(tmp_path, rows)
    assert [r["name"] for r in cleaned(result)] == names


def test_xlsx_cells_are_cleaned_like_csv(tmp_path):
    """
    tests typed XLSX cells: text identifiers keep zeros, numbers stay exact,
    native dates need no format, and empty cells are blank
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADER)
    sheet.append(["000123", "Oats", 19.99, 4, date(2026, 10, 5)])
    sheet.append([1042, " Mug ", 2, None, "10/05/2026"])
    path = tmp_path / "items.xlsx"
    workbook.save(path)

    result = clean_table(table_profile("clean"), path)
    assert cleaned(result) == [
        {
            "sku": "000123",
            "name": "Oats",
            "price": "19.99",
            "qty": "4",
            "counted": "2026-10-05",
        },
        {
            "sku": "1042",
            "name": "Mug",
            "price": "2.00",
            "qty": "",
            "counted": "2026-10-05",
        },
    ]


def test_malformed_rows_are_rejected(tmp_path):
    """
    tests that rows with the wrong number of cells are skipped and reported
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    path = tmp_path / "items.csv"
    path.write_text(
        "SKU,Name,Price,Qty,Counted\nSKU-1,Mug,1,,\nSKU-2,Mug,1,,,extra\n",
        encoding="utf-8",
    )
    result = clean_table(table_profile("clean"), path)
    assert len(result.records) == 1
    assert codes(result) == [(3, "malformed_row")]
    assert result.counts()["rows_read"] == 2


def test_cleaning_never_modifies_the_input(tmp_path):
    """
    tests that the source file bytes and timestamp are untouched
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    path = write_table(tmp_path / "items.csv", [[" SKU-1 ", "Mug", "$1", "", ""]])
    before = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
    result = clean_table(table_profile("clean"), path)
    after = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
    assert before == after
    assert result.input.sha256 == before[0]


@pytest.mark.parametrize(
    ("name", "content", "expected"),
    [
        ("items.csv", b"", "is empty"),
        ("items.csv", b"SKU,Name\xff\n", "not valid utf-8-sig"),
        ("items.txt", b"SKU\n", "accepted formats"),
        ("items.xlsx", b"not a workbook", "could not be opened as XLSX"),
    ],
)
def test_unreadable_inputs_fail_safely(tmp_path, name, content, expected):
    """
    tests that unreadable files raise an input error naming the problem
    :param tmp_path: pytest temporary directory
    :param name: file name
    :param content: file bytes
    :param expected: text expected in the error
    :returns: none
    """
    path = tmp_path / name
    path.write_bytes(content)
    with pytest.raises(InputError, match=expected):
        clean_table(table_profile("clean"), path)


def test_missing_input_fails_safely(tmp_path):
    """
    tests that a missing file is an input error
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    with pytest.raises(InputError, match="input file not found"):
        clean_table(table_profile("clean"), tmp_path / "nope.csv")


def test_cleaning_without_a_key_keeps_identical_keys(tmp_path):
    """
    tests that without a key only exact duplicates are removed
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    rows = [["SKU-1", "Mug", "1", "", ""], ["SKU-1", "Mug", "2", "", ""]]
    result = clean_rows(tmp_path, rows, key=[])
    assert len(result.records) == 2
    assert result.conflicting_keys == set()
