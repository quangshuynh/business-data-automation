"""
guided walkthrough of spreadsheet cleaning and comparison on the fictional
Saltmarsh Mercantile weekly inventory exports

run with: python -m app.ordixa.inventory_demo
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.ordixa.cli import (
    ASSESSMENT_TEXT,
    EXIT_INTEGRITY,
    EXIT_OK,
    EXIT_OUTPUT,
    PROJECT_ROOT,
    check_output_location,
    report,
)
from app.ordixa.demo import relative
from app.ordixa.manifest import verify_run
from app.ordixa.tabular import clean_table, compare_tables
from app.ordixa.tabular_outputs import (
    CLEAN_ISSUES_NAME,
    CLEANED_NAME,
    REPORT_NAME,
    write_clean_run,
    write_compare_run,
)
from app.ordixa.tabular_profile import load_table_profile

DEMO_INPUT = PROJECT_ROOT / "examples" / "ordixa" / "exports" / "inventory"
BEFORE = DEMO_INPUT / "inventory-before.csv"
AFTER = DEMO_INPUT / "inventory-after.csv"
PROFILES = PROJECT_ROOT / "examples" / "ordixa" / "profiles"
CLEAN_PROFILE = PROFILES / "inventory-clean.toml"
COMPARE_PROFILE = PROFILES / "inventory-compare.toml"
DEFAULT_OUT = PROJECT_ROOT / "output" / "inventory-demo"
STEPS = 5


def step(number, title):
    """
    prints a numbered step heading
    :param number: step number
    :param title: step title
    :returns: none
    """
    print(f"\n[{number}/{STEPS}] {title}\n" + "-" * (len(title) + 6))


def build_parser():
    """
    defines the demo command line
    :returns: argument parser
    """
    parser = argparse.ArgumentParser(
        prog="python -m app.ordixa.inventory_demo",
        description="Clean and compare the fictional Saltmarsh Mercantile exports.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"parent directory for the runs (default {relative(DEFAULT_OUT)})",
    )
    return parser


def show_checks(run_dir, inputs):
    """
    verifies a run and prints each check
    :param run_dir: run directory
    :param inputs: input files to re-check
    :returns: true when every check passed
    """
    checks = verify_run(run_dir, inputs)
    for description, passed in checks:
        print(f"  {'ok  ' if passed else 'FAIL'} {description}")
    return all(passed for _, passed in checks)


def main(argv=None):
    """
    cleans the earlier export, compares both weeks, and verifies both runs
    :param argv: optional argument list
    :returns: process exit code
    """
    args = build_parser().parse_args(argv)
    started_at = datetime.now(timezone.utc)
    print("Ordixa inventory demo - Saltmarsh Mercantile (fictional), October 2026")
    print("Less busywork. More clarity.")

    step(1, "Weekly inventory exports")
    for path in (BEFORE, AFTER):
        print(f"  {path.name:<24} {path.stat().st_size:>6,} bytes")
    print(f"  location: {relative(DEMO_INPUT)}")
    print(f"  profiles: {relative(CLEAN_PROFILE)}, {relative(COMPARE_PROFILE)}")

    try:
        check_output_location(args.out / "clean", DEMO_INPUT)
    except OSError as error:
        report(f"output error: {error}", sys.stderr)
        return EXIT_OUTPUT

    step(2, "Clean the earlier export")
    clean_profile = load_table_profile(CLEAN_PROFILE, "clean")
    cleaned = clean_table(clean_profile, BEFORE)
    clean_dir, _ = write_clean_run(cleaned, args.out / "clean", started_at)
    counts = cleaned.counts()
    print(
        f"  {counts['rows_read']} rows read, {counts['rows_written']} written, "
        f"{counts['duplicate_rows_removed']} exact duplicate removed, "
        f"{counts['rows_rejected']} rejected"
    )
    print(
        f"  {counts['whitespace_normalized']} padded cells trimmed, "
        f"{counts['blank_tokens_normalized']} placeholders blanked, "
        f"{counts['values_reformatted']} prices and dates standardized"
    )
    print(f"  {len(cleaned.unmapped_columns)} unmapped column left out of the outputs")
    print(f"  cleaned data: {relative(clean_dir / CLEANED_NAME)}")
    print(f"  issue report: {relative(clean_dir / CLEAN_ISSUES_NAME)}")

    step(3, "Compare the two weeks by SKU")
    compare_profile = load_table_profile(COMPARE_PROFILE, "compare")
    result = compare_tables(compare_profile, BEFORE, AFTER)
    compare_dir, manifest = write_compare_run(result, args.out / "compare", started_at)
    totals = result.counts()
    print(
        f"  {totals['added']} added, {totals['removed']} removed, "
        f"{totals['modified']} modified, {totals['unchanged']} unchanged"
    )
    by_column = totals["changed_values_by_column"]
    print(
        f"  {by_column.get('unit_price', 0)} price changes, "
        f"{by_column.get('quantity_on_hand', 0)} stock changes"
    )
    print(
        f"  {totals['ambiguous_keys']} SKU with conflicting rows and "
        f"{totals['invalid_keys']} SKUs with rejected rows held back; "
        f"{totals['unkeyed_rejected_rows']} row without a SKU"
    )
    assessment = manifest["result"]["assessment"]
    print(f"  result: {ASSESSMENT_TEXT[assessment['level']]}")
    for item in assessment["findings"]:
        print(f"    {item['level']}: {item['message']}")

    step(4, "Change report workbook")
    print(f"  open {relative(compare_dir / REPORT_NAME)}")
    print(
        "  Summary - comparison result, record counts, changes by column, inputs "
        "and checksums"
    )
    print("  Added / Removed Records - SKUs found in only one week")
    print("  Modified Records - each changed column with previous and new value")
    print("  Data Quality Issues - every held-back row and why")

    step(5, "Manifest verification")
    clean_ok = show_checks(clean_dir, [BEFORE])
    compare_ok = show_checks(compare_dir, [BEFORE, AFTER])
    print(f"  comparison fingerprint {manifest['result']['result_fingerprint']}")

    if not (clean_ok and compare_ok):
        print("\nverification failed; do not rely on these runs", file=sys.stderr)
        return EXIT_INTEGRITY
    print(f"\nDemo complete. Runs: {relative(clean_dir)}, {relative(compare_dir)}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
