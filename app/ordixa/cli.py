import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.ordixa import __version__
from app.ordixa.issues import InputError
from app.ordixa.manifest import MANIFEST_NAME, WORKBOOK_NAME, write_run_outputs
from app.ordixa.pipeline import ReconciliationIntegrityError, process
from app.ordixa.profile import ProfileError, load_profile

EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_USAGE = 2
EXIT_INPUT = 3
EXIT_INTEGRITY = 4
EXIT_OUTPUT = 5

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# tracked directories that a run must never write into
PROTECTED_DIRS = ("examples", "data", "tests", "app")


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

    check = commands.add_parser("check-profile", help="validate a profile only")
    check.add_argument("--profile", required=True, type=Path, help="TOML profile")
    return parser


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
    result = process(profile, args.input)
    for item in result.inputs:
        report(f"read {item.role}: {item.name} ({item.data_rows} rows)")
    if result.ignored_files:
        report(f"ignored {len(result.ignored_files)} file(s) matching no dataset")
    if "customers" not in result.records:
        report("no customers file provided; orders reconciled without customer data")

    run_dir, manifest = write_run_outputs(result, args.out, started_at)
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
    return EXIT_OK


def main(argv=None):
    """
    command line entry point
    :param argv: optional argument list
    :returns: process exit code
    """
    args = build_parser().parse_args(argv)

    try:
        if args.command == "check-profile":
            profile = load_profile(args.profile)
            report(f"profile {profile.name} {profile.version} is valid")
            return EXIT_OK
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
        report(f"unexpected error: {type(error).__name__}: {error}", sys.stderr)
        return EXIT_UNEXPECTED
