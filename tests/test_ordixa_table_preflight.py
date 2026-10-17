"""
tests for the read-only clean/compare preflight and check-profile --explain
"""

import json
import unicodedata

import pytest
from ordixa_helpers import PROFILE_PATH, write_rows
from table_helpers import (
    CLEAN_PROFILE,
    COMPARE_PROFILE,
    HEADER,
    INVENTORY_DIR,
    table_profile,
    write_table,
)

from app.ordixa import cli
from app.ordixa.preflight import looks_personal
from app.ordixa.table_preflight import (
    ambiguous_date_formats,
    format_table_preflight,
    table_preflight,
)

BEFORE = INVENTORY_DIR / "inventory-before.csv"
AFTER = INVENTORY_DIR / "inventory-after.csv"
ROWS = [
    ["SKU-1", "Mug", "4.50", "10", "2026-01-05"],
    ["SKU-2", "Bowl", "7.00", "3", "2026-01-05"],
]
SENTINEL = "Zebulon Quartzfield"


def run_cli(*args):
    """
    invokes the CLI entry point in-process
    :param args: command line arguments
    :returns: exit code
    """
    return cli.main([str(arg) for arg in args])


def codes(report, level=None):
    """
    lists finding codes, optionally of one level
    :param report: preflight report
    :param level: blocking, warning, note, or none for all
    :returns: list of codes
    """
    return [
        item["code"]
        for item in report["findings"]
        if level is None or item["level"] == level
    ]


def snapshot(directory):
    """
    records every file under a directory with its size and modification time
    :param directory: directory to scan
    :returns: dictionary
    """
    return {
        path: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in directory.rglob("*")
    }


def test_clean_preflight_reports_counts_and_writes_nothing(tmp_path):
    """
    tests the single-file preflight against the fictional inventory export
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    before = snapshot(INVENTORY_DIR)
    profile = table_profile("clean")
    path = write_table(tmp_path / "items.csv", ROWS)
    files = snapshot(tmp_path)

    report = table_preflight(profile, [("input", path)])
    assert report["readiness"] == "ready"
    assert report["profile"]["kind"] == "clean"
    assert report["key"] == ["sku"]
    (entry,) = report["inputs"]
    assert entry["counts"]["rows_read"] == 2
    assert entry["counts"]["rows_written"] == 2
    assert snapshot(tmp_path) == files
    assert snapshot(INVENTORY_DIR) == before


def test_every_missing_column_is_reported_at_once(tmp_path):
    """
    tests that required mapped headers are listed together with hints
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    path = write_rows(
        tmp_path / "items.csv", ["SKU", "Product", "Qty"], [["SKU-1", "Mug", "1"]]
    )
    report = table_preflight(table_profile("clean"), [("input", path)])
    assert report["readiness"] == "blocked"
    (missing,) = [f for f in report["findings"] if f["code"] == "missing_column"]
    assert "'Name'" in missing["message"] and "'Price'" in missing["message"]
    assert report["inputs"][0]["counts"] is None


def test_missing_optional_and_unexpected_columns_are_named(tmp_path):
    """
    tests optional-column and unmapped-header findings by header name
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    path = write_rows(
        tmp_path / "items.csv",
        ["SKU", "Name", "Price", "Counted", "Shelf"],
        [["SKU-1", "Mug", "1.00", "", "A3"]],
    )
    report = table_preflight(table_profile("clean"), [("input", path)])
    assert report["readiness"] == "review"
    (optional,) = [
        f for f in report["findings"] if f["code"] == "optional_column_missing"
    ]
    assert optional["level"] == "warning" and "'Qty'" in optional["message"]
    (unused,) = [f for f in report["findings"] if f["code"] == "unused_column"]
    assert "Shelf" in unused["message"]


@pytest.mark.parametrize("mapped", [False, True])
def test_prohibited_headers_block_whether_mapped_or_not(tmp_path, mapped):
    """
    tests that card, bank, or ID-looking headers stop the preflight
    :param tmp_path: pytest temporary directory
    :param mapped: whether the profile maps the column
    :returns: none
    """

    def mutate(document):
        if mapped:
            document["columns"]["card"] = {"source": "Card Number"}

    path = write_rows(
        tmp_path / "items.csv",
        [*HEADER, "Card Number"],
        [[*ROWS[0], "4111111111111111"]],
    )
    report = table_preflight(table_profile("clean", mutate), [("input", path)])
    assert report["readiness"] == "blocked"
    assert "prohibited_column" in codes(report, "blocking")
    assert "4111" not in json.dumps(report)


def test_broad_blank_tokens_and_ambiguous_dates_are_risks(tmp_path):
    """
    tests profile-only normalization risks
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    profile = table_profile(
        "clean",
        blank_values=["N/A", "0"],
        date_formats=["%m/%d/%Y", "%d/%m/%Y"],
    )
    path = write_table(tmp_path / "items.csv", ROWS)
    report = table_preflight(profile, [("input", path)])
    warnings = codes(report, "warning")
    assert "blank_token_is_a_value" in warnings
    assert "ambiguous_date_formats" in warnings
    (token,) = [f for f in report["findings"] if f["code"] == "blank_token_is_a_value"]
    assert "'0'" in token["message"] and "qty" in token["message"]
    assert ambiguous_date_formats(["%Y-%m-%d", "%m/%d/%Y"]) == []


def test_blank_token_in_a_key_column_is_counted(tmp_path):
    """
    tests the data-driven blank token finding for business keys
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    path = write_table(tmp_path / "items.csv", [*ROWS, ["N/A", "Lid", "1.00", "1", ""]])
    report = table_preflight(table_profile("clean"), [("input", path)])
    (finding,) = [f for f in report["findings"] if f["code"] == "blank_token_in_key"]
    assert finding["message"].startswith("1 row(s)") and "sku" in finding["message"]


def test_decomposed_unicode_is_reported_without_values(tmp_path):
    """
    tests the Unicode-form finding
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    name = unicodedata.normalize("NFD", SENTINEL + "é")
    path = write_table(tmp_path / "items.csv", [["SKU-1", name, "1.00", "1", ""]])
    report = table_preflight(table_profile("clean"), [("input", path)])
    assert "decomposed_unicode" in codes(report, "warning")
    assert "Zebulon" not in json.dumps(report, ensure_ascii=False)


def test_compare_preview_includes_the_assessment():
    """
    tests the before/after preview on the fictional inventory exports
    :returns: none
    """
    from app.ordixa.tabular_profile import load_table_profile

    profile = load_table_profile(COMPARE_PROFILE)
    report = table_preflight(profile, [("before", BEFORE), ("after", AFTER)])
    assert report["comparison"]["added"] == 6
    assert report["comparison"]["modified"] == 19
    assert report["assessment"]["level"] == "incomplete"
    assert {"ignored_columns", "ignored_column_differs", "unclassified_keys"} <= set(
        codes(report, "warning")
    )
    assert report["readiness"] == "review"
    text = format_table_preflight(report)
    assert "result: INCOMPLETE" in text and "6 added, 4 removed" in text


def test_optional_column_missing_from_one_comparison_input(tmp_path):
    """
    tests that the preview warns before a comparison would be incomplete
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    before = write_table(tmp_path / "before.csv", ROWS)
    after = write_rows(
        tmp_path / "after.csv",
        ["SKU", "Name", "Price", "Counted"],
        [[r[0], r[1], r[2], r[4]] for r in ROWS],
    )
    report = table_preflight(table_profile(), [("before", before), ("after", after)])
    assert "column_missing_from_one_export" in codes(report, "warning")
    assert "optional_column_missing" not in codes(report)
    assert report["assessment"]["level"] == "incomplete"


def test_business_name_headers_are_not_personal():
    """
    tests the narrowed personal-data header heuristic
    :returns: none
    """
    assert not looks_personal("Product Name")
    assert not looks_personal("supplier_name")
    assert looks_personal("Customer Name")
    assert looks_personal("Name")
    assert looks_personal("Email")


def test_explain_shows_mapping_and_normalization(capsys):
    """
    tests check-profile --explain for a compare preview
    :param capsys: pytest capture fixture
    :returns: none
    """
    code = run_cli(
        "check-profile",
        "--profile",
        COMPARE_PROFILE,
        "--before",
        BEFORE,
        "--after",
        AFTER,
        "--explain",
    )
    assert code == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "'Item SKU'" in out and "-> sku" in out
    assert "identifier, required, key, found" in out
    assert "not compared" in out and "ignored     last_counted" in out
    assert "cells holding exactly '-', 'N/A', 'n/a'" in out
    assert "Readiness: REVIEW" in out
    assert "result: INCOMPLETE" in out


def test_explain_json_and_preflight_together(capsys):
    """
    tests that --explain --json is one parseable document with both parts
    :param capsys: pytest capture fixture
    :returns: none
    """
    code = run_cli(
        "check-profile",
        "--profile",
        CLEAN_PROFILE,
        "--input",
        AFTER,
        "--explain",
        "--json",
    )
    assert code == cli.EXIT_OK
    document = json.loads(capsys.readouterr().out)
    assert document["rows_written"] == 119
    assert document["readiness"] == "review"
    columns = {c["output"]: c for c in document["explain"]["columns"]}
    assert columns["sku"]["source"] == "Item SKU"
    assert columns["sku"]["found_in"] == {"input": True}
    assert document["explain"]["profile"]["kind"] == "clean"


def test_explain_without_input_explains_the_profile_only(capsys):
    """
    tests --explain on a profile with no files
    :param capsys: pytest capture fixture
    :returns: none
    """
    assert run_cli("check-profile", "--profile", CLEAN_PROFILE, "--explain") == 0
    out = capsys.readouterr().out
    assert "Column mapping" in out and "Preflight" not in out
    assert (
        run_cli("check-profile", "--profile", PROFILE_PATH, "--explain", "--json") == 0
    )
    explanation = json.loads(capsys.readouterr().out)["explain"]
    assert explanation["profile"]["kind"] == "reconciliation"
    assert "orders" in explanation["datasets"]


def test_reconciliation_explain_lists_datasets(capsys):
    """
    tests the reconciliation explanation text
    :param capsys: pytest capture fixture
    :returns: none
    """
    assert run_cli("check-profile", "--profile", PROFILE_PATH, "--explain") == 0
    out = capsys.readouterr().out
    assert "How this profile reads an export batch" in out
    assert "-> order_id" in out and "payments (required" in out


def test_explain_never_overrides_a_blocked_preflight(tmp_path, capsys):
    """
    tests that a preview still fails when the file cannot be processed
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :returns: none
    """
    path = write_rows(tmp_path / "items.csv", ["Wrong"], [["x"]])
    code = run_cli(
        "check-profile", "--profile", CLEAN_PROFILE, "--input", path, "--explain"
    )
    assert code == cli.EXIT_INPUT
    out = capsys.readouterr().out
    assert "MISSING in input" in out and "Readiness: BLOCKED" in out


def test_preview_output_never_shows_cell_values(tmp_path, capsys):
    """
    tests that preflight and explain output carry no cell values
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :returns: none
    """
    header = ["Item SKU", "Product Name", "Unit Price", "Qty On Hand", "Supplier"]
    rows = [
        ["SKU-1", SENTINEL, "bad", "1", SENTINEL],
        ["SKU-2", SENTINEL, "1", "x", ""],
    ]
    before = write_rows(tmp_path / "before.csv", header, rows)
    after = write_rows(tmp_path / "after.csv", header, rows[::-1])
    for extra in ([], ["--json"]):
        run_cli(
            "check-profile",
            "--profile",
            COMPARE_PROFILE,
            "--before",
            before,
            "--after",
            after,
            "--explain",
            *extra,
        )
        captured = capsys.readouterr()
        assert "Zebulon" not in captured.out + captured.err


@pytest.mark.parametrize(
    "args",
    [
        ["--profile", COMPARE_PROFILE, "--before", BEFORE],
        [
            "--profile",
            COMPARE_PROFILE,
            "--before",
            BEFORE,
            "--after",
            AFTER,
            "--input",
            AFTER,
        ],
        ["--profile", CLEAN_PROFILE, "--before", BEFORE, "--after", AFTER],
        ["--profile", PROFILE_PATH, "--before", BEFORE, "--after", AFTER],
        ["--profile", CLEAN_PROFILE, "--json"],
    ],
)
def test_invalid_check_profile_combinations_are_usage_errors(args, capsys):
    """
    tests argument validation for the preview options
    :param args: check-profile arguments
    :param capsys: pytest capture fixture
    :returns: none
    """
    assert run_cli("check-profile", *args) == cli.EXIT_USAGE
    assert capsys.readouterr().err.startswith("ordixa: ")
