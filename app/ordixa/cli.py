import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.ordixa import __version__
from app.ordixa.inspection import (
    DEFAULT_MAX_ROWS,
    MAX_PREVIEW_ROWS,
    format_report,
    inspect_path,
)
from app.ordixa.issues import InputError
from app.ordixa.manifest import MANIFEST_NAME, WORKBOOK_NAME, write_run_outputs
from app.ordixa.pipeline import ReconciliationIntegrityError, process
from app.ordixa.preflight import format_preflight, preflight
from app.ordixa.profile import ProfileError, load_profile

EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_USAGE = 2
EXIT_INPUT = 3
EXIT_INTEGRITY = 4
EXIT_OUTPUT = 5

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# tracked directories that a run must never write into
PROTECTED_DIRS = ("examples", "data", "tests", "app", "docs")
# git-ignored directories where customer files and run outputs may live
IGNORED_DIRS = ("output", "customer-data")


def report(message, stream=None):
    """
    prints a concise progress or error message
    :param message: text to print
    :param stream: output stream, defaults to standard output
    :returns: none
    """
    print(f"ordixa: {message}", file=stream or sys.stdout)


def is_within(path, parent):
    """
    checks whether a path is inside another directory
    :param path: candidate path
    :param parent: parent directory
    :returns: true when path is parent or a descendant
    """
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def check_output_location(out_dir, input_dir):
    """
    refuses output locations that would mix results with source data
    :param out_dir: requested output directory
    :param input_dir: input export directory
    :returns: none
    """
    if is_within(out_dir, input_dir):
        raise OSError(
            f"output directory {out_dir} is inside the input directory; "
            "choose a separate location"
        )
    for name in PROTECTED_DIRS:
        if is_within(out_dir, PROJECT_ROOT / name):
            raise OSError(
                f"output directory {out_dir} is inside the tracked {name}/ "
                "directory; choose a location such as output/"
            )
    if is_within(out_dir, PROJECT_ROOT) and not any(
        is_within(out_dir, PROJECT_ROOT / name) for name in IGNORED_DIRS
    ):
        raise OSError(
            f"output directory {out_dir} is inside the repository but not in a "
            "git-ignored folder; use output/ or a location outside the repository"
        )


def warn_about_input_location(input_dir):
    """
    warns when exports sit in the repository where they could be committed
    :param input_dir: input export directory
    :returns: none
    """
    if not is_within(input_dir, PROJECT_ROOT):
        return
    if any(
        is_within(input_dir, PROJECT_ROOT / name)
        for name in ("examples", "tests", *IGNORED_DIRS)
    ):
        return
    report(
        f"warning: {input_dir} is inside the repository and not git-ignored; keep "
        "customer exports outside the repository or in customer-data/",
        sys.stderr,
    )


def build_parser():
    """
    defines the command line interface
    :returns: argument parser
    """
    parser = argparse.ArgumentParser(
        prog="python -m app.ordixa",
        description="Profile-driven import, validation, and reconciliation.",
    )
    parser.add_argument("--version", action="version", version=f"ordixa {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser(
        "run", help="process an export directory and write a run directory"
    )
    run.add_argument("--profile", required=True, type=Path, help="TOML profile")
    run.add_argument(
        "--input", required=True, type=Path, help="directory containing the exports"
    )
    run.add_argument(
        "--out",
        required=True,
        type=Path,
        help="parent directory; each run creates a new run-<id> folder inside it",
    )

    check = commands.add_parser(
        "check-profile",
        help="validate a profile, optionally against a batch of exports",
        description=(
            "Validates the profile. With --input, also runs a read-only pilot "
            "preflight: every missing file, missing column, unused or "
            "personal-data column, and row-outcome count, without writing files "
            "or printing cell values."
        ),
    )
    check.add_argument("--profile", required=True, type=Path, help="TOML profile")
    check.add_argument(
        "--input", type=Path, help="export directory to preflight against the profile"
    )
    check.add_argument(
        "--json", action="store_true", help="print the preflight report as JSON"
    )

    inspect = commands.add_parser(
        "inspect",
        help="describe unfamiliar CSV/XLSX exports before writing a profile",
        description=(
            "Read-only. Reports worksheets, headers, row counts, and suggested "
            "column types without printing cell values or writing any files."
        ),
    )
    inspect.add_argument(
        "--input", required=True, type=Path, help="export file or directory"
    )
    inspect.add_argument(
        "--encoding", default="utf-8-sig", help="CSV text encoding (utf-8-sig)"
    )
    inspect.add_argument(
        "--max-rows",
        type=positive_int,
        default=DEFAULT_MAX_ROWS,
        help=f"data rows to scan per table (default {DEFAULT_MAX_ROWS})",
    )
    inspect.add_argument(
        "--preview",
        type=positive_int,
        default=0,
        metavar="ROWS",
        help=(
            f"show up to {MAX_PREVIEW_ROWS} rows redacted to character shapes "
            "(letters as A/a, digits as 9); off by default"
        ),
    )
    inspect.add_argument("--json", action="store_true", help="print the report as JSON")
    return parser


def positive_int(text):
    """
    parses a positive integer command line value
    :param text: argument text
    :returns: integer
    """
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number") from None
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def inspect_command(args):
    """
    executes the read-only inspect subcommand
    :param args: parsed arguments
    :returns: exit code
    """
    try:
        reports = inspect_path(args.input, args.encoding, args.max_rows, args.preview)
    except LookupError:
        report(f"unknown encoding {args.encoding!r}", sys.stderr)
        return EXIT_USAGE
    except FileNotFoundError:
        report(f"input error: {args.input} does not exist", sys.stderr)
        return EXIT_INPUT

    if args.json:
        print(json.dumps({"files": reports}, indent=2, ensure_ascii=False))
    else:
        print(format_report(reports, args.max_rows))
    return EXIT_INPUT if any(item["errors"] for item in reports) else EXIT_OK


def check_profile_command(args):
    """
    executes the check-profile subcommand and its optional preflight
    :param args: parsed arguments
    :returns: exit code
    """
    if args.json and args.input is None:
        report("--json needs --input", sys.stderr)
        return EXIT_USAGE
    profile = load_profile(args.profile)
    if not args.json:
        # keeps --json output parseable as a single document
        report(f"profile {profile.name} {profile.version} is valid")
    if args.input is None:
        return EXIT_OK

    warn_about_input_location(args.input)
    result = preflight(profile, args.input)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_preflight(result))
    return EXIT_INPUT if result["readiness"] == "blocked" else EXIT_OK


def run_command(args):
    """
    executes the run subcommand
    :param args: parsed arguments
    :returns: exit code
    """
    started_at = datetime.now(timezone.utc)
    profile = load_profile(args.profile)
    report(f"profile {profile.name} {profile.version} is valid")

    check_output_location(args.out, args.input)
    warn_about_input_location(args.input)
    result = process(profile, args.input)
    for item in result.inputs:
        report(f"read {item.role}: {item.name} ({item.data_rows} rows)")
    if result.ignored_files:
        report(f"ignored {len(result.ignored_files)} file(s) matching no dataset")
    if "customers" not in result.records:
        report("no customers file provided; orders reconciled without customer data")

    run_dir, manifest = write_run_outputs(result, args.out, started_at)
    report_run(result, run_dir, manifest)
    return EXIT_OK


def report_run(result, run_dir, manifest):
    """
    prints the headline outcome of a finished run
    :param result: run result
    :param run_dir: run directory
    :param manifest: manifest dictionary
    :returns: none
    """
    profile = result.profile
    summary = result.summary
    counts = summary["status_counts"]
    currency = profile.amounts.currency
    report(
        f"{summary['orders']} orders reconciled: {counts['paid']} paid, "
        f"{counts['partial']} partial, {counts['unpaid']} unpaid, "
        f"{counts['overpaid']} overpaid"
    )
    report(
        f"net received {summary['net_received']} {currency}; outstanding "
        f"{summary['outstanding_balance']} {currency}"
    )
    report(
        f"{summary['rejected_rows']} row(s) rejected, {summary['warning_rows']} kept "
        f"with warnings, {summary['excluded_rows']} excluded by profile"
    )
    report(f"workbook: {run_dir / WORKBOOK_NAME}")
    report(f"manifest: {run_dir / MANIFEST_NAME} ({manifest['result']['status']})")


def main(argv=None):
    """
    command line entry point
    :param argv: optional argument list
    :returns: process exit code
    """
    args = build_parser().parse_args(argv)

    try:
        if args.command == "inspect":
            return inspect_command(args)
        if args.command == "check-profile":
            return check_profile_command(args)
        return run_command(args)
    except ProfileError as error:
        report(str(error), sys.stderr)
        return EXIT_USAGE
    except InputError as error:
        report(f"input error: {error}", sys.stderr)
        return EXIT_INPUT
    except ReconciliationIntegrityError as error:
        report(f"integrity check failed, no outputs written: {error}", sys.stderr)
        return EXIT_INTEGRITY
    except OSError as error:
        report(f"output error: {error}", sys.stderr)
        return EXIT_OUTPUT
    except Exception as error:  # last-resort guard so automation sees a code
        # library messages can quote cell values, so details are opt-in
        details = (
            f": {error}"
            if os.environ.get("ORDIXA_DEBUG")
            else " (details withheld because they may contain row values; set "
            "ORDIXA_DEBUG=1 to show them)"
        )
        report(f"unexpected error: {type(error).__name__}{details}", sys.stderr)
        report("no run directory was kept", sys.stderr)
        return EXIT_UNEXPECTED
