"""
guided walkthrough of Ordixa on the fictional Harbor Lane Supply Co. exports

run with: python -m app.ordixa.demo
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.ordixa.cli import (
    EXIT_INTEGRITY,
    EXIT_OK,
    EXIT_OUTPUT,
    PROJECT_ROOT,
    check_output_location,
    report,
    report_run,
)
from app.ordixa.inspection import DEFAULT_MAX_ROWS, format_report, inspect_path
from app.ordixa.manifest import WORKBOOK_NAME, verify_run, write_run_outputs
from app.ordixa.pipeline import process
from app.ordixa.profile import load_profile

DEMO_INPUT = PROJECT_ROOT / "examples" / "ordixa" / "exports" / "demo"
DEMO_PROFILE = PROJECT_ROOT / "examples" / "ordixa" / "profiles" / "harbor-lane.toml"
DEFAULT_OUT = PROJECT_ROOT / "output" / "demo"
STEPS = 7


def step(number, title):
    """
    prints a numbered step heading
    :param number: step number
    :param title: step title
    :returns: none
    """
    print(f"\n[{number}/{STEPS}] {title}\n" + "-" * (len(title) + 6))


def relative(path):
    """
    shows a path relative to the repository when possible
    :param path: path to display
    :returns: display text
    """
    try:
        return str(Path(path).resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def build_parser():
    """
    defines the demo command line
    :returns: argument parser
    """
    parser = argparse.ArgumentParser(
        prog="python -m app.ordixa.demo",
        description="Run the fictional Harbor Lane Supply Co. demonstration.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"parent directory for the run (default {relative(DEFAULT_OUT)})",
    )
    parser.add_argument(
        "--skip-inspect",
        action="store_true",
        help="leave out the read-only inspection report",
    )
    return parser


def main(argv=None):
    """
    runs every demo step and verifies the result
    :param argv: optional argument list
    :returns: process exit code
    """
    args = build_parser().parse_args(argv)
    started_at = datetime.now(timezone.utc)
    print("Ordixa demo - Harbor Lane Supply Co. (fictional), October 2026")
    print("Less busywork. More clarity.")

    step(1, "Source exports")
    for path in sorted(DEMO_INPUT.iterdir()):
        print(f"  {path.name:<24} {path.stat().st_size:>6,} bytes")
    print(f"  location: {relative(DEMO_INPUT)}")

    step(2, "Read-only inspection")
    if args.skip_inspect:
        print("  skipped (--skip-inspect)")
    else:
        reports = inspect_path(DEMO_INPUT)
        print(format_report(reports, DEFAULT_MAX_ROWS))

    step(3, "Customer import profile")
    print(f"  {relative(DEMO_PROFILE)}")
    print("  maps storefront and processor headers, ID prefixes, date formats,")
    print("  status labels, and refund signs onto Ordixa's canonical fields")

    step(4, "Profile validation")
    profile = load_profile(DEMO_PROFILE)
    print(f"  profile {profile.name} {profile.version} is valid")
    print(f"  SHA-256 {profile.sha256}")

    step(5, "Processing and reconciliation")
    try:
        check_output_location(args.out, DEMO_INPUT)
    except OSError as error:
        report(f"output error: {error}", sys.stderr)
        return EXIT_OUTPUT
    result = process(profile, DEMO_INPUT)
    run_dir, manifest = write_run_outputs(result, args.out, started_at)
    report_run(result, run_dir, manifest)

    step(6, "Exceptions workbook")
    print(f"  open {relative(run_dir / WORKBOOK_NAME)}")
    print("  Summary - totals, exception counts, data quality, input fingerprints")
    print("  Exceptions - unpaid, partial, and overpaid orders to follow up")
    print("  Rejected Rows - every rejected, warned, or excluded row and why")
    print("  Full Ledger - every reconciled order with its transactions")

    step(7, "Manifest and result verification")
    checks = verify_run(run_dir, DEMO_INPUT)
    for description, passed in checks:
        print(f"  {'ok  ' if passed else 'FAIL'} {description}")
    print(f"  result fingerprint {manifest['result']['result_fingerprint']}")

    if not all(passed for _, passed in checks):
        print("\nverification failed; do not rely on this run", file=sys.stderr)
        return EXIT_INTEGRITY
    print(f"\nDemo complete. Run directory: {relative(run_dir)}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
