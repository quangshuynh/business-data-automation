import csv
import hashlib
import json
import subprocess
import sys
from decimal import Decimal

import pytest
from ordixa_golden import CLEAN_LEDGER
from ordixa_helpers import EXPORTS_DIR, PROFILE_PATH, ROOT, copy_exports, csv_to_xlsx

from app.ordixa import cli, pipeline
from app.ordixa.manifest import LEDGER_NAME, MANIFEST_NAME, WORKBOOK_NAME


def run_cli(*args):
    """
    invokes the CLI entry point in-process
    :param args: command line arguments
    :returns: exit code
    """
    return cli.main([str(arg) for arg in args])


def run_dirs(out_dir):
    """
    lists run directories created under an output directory
    :param out_dir: parent output directory
    :returns: sorted list of run directories
    """
    if not out_dir.exists():
        return []
    return sorted(path for path in out_dir.iterdir() if path.name.startswith("run-"))


def ledger_from_csv(run_dir):
    """
    reads the ledger CSV artifact into golden-comparable tuples
    :param run_dir: run directory
    :returns: mapping of order id to golden tuple
    """
    with (run_dir / LEDGER_NAME).open(encoding="utf-8", newline="") as handle:
        return {
            int(row["order_id"]): (
                Decimal(row["order_total"]),
                Decimal(row["net_paid"]),
                row["financial_status"],
                Decimal(row["outstanding_balance"]),
                Decimal(row["overpayment_amount"]),
            )
            for row in csv.DictReader(handle)
        }


def digest_tree(directory):
    """
    fingerprints every file in a directory
    :param directory: directory to hash
    :returns: mapping of file name to SHA-256 digest
    """
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.iterdir())
    }


def test_run_succeeds_on_clean_exports(tmp_path, capsys, monkeypatch):
    """
    tests the successful CLI path without any database configuration
    :param tmp_path: pytest temporary directory
    :param capsys: pytest output capture
    :param monkeypatch: pytest fixture for environment changes
    :returns: none
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unused@invalid/none")
    input_dir = copy_exports("clean", tmp_path / "in")
    before = digest_tree(input_dir)

    code = run_cli(
        "run",
        "--profile",
        PROFILE_PATH,
        "--input",
        input_dir,
        "--out",
        tmp_path / "out",
    )

    output = capsys.readouterr().out
    created = run_dirs(tmp_path / "out")
    assert code == cli.EXIT_OK
    assert len(created) == 1
    assert (created[0] / WORKBOOK_NAME).exists()
    assert ledger_from_csv(created[0]) == CLEAN_LEDGER
    assert "profile harbor-lane 1.0.0 is valid" in output
    assert "9 orders reconciled: 3 paid, 2 partial, 3 unpaid, 1 overpaid" in output
    assert "net received 3752.23 USD; outstanding 467.90 USD" in output
    assert digest_tree(input_dir) == before


def test_run_reports_rejections_but_still_succeeds(tmp_path, capsys):
    """
    tests that row-level rejections do not fail the run
    :param tmp_path: pytest temporary directory
    :param capsys: pytest output capture
    :returns: none
    """
    code = run_cli(
        "run",
        "--profile",
        PROFILE_PATH,
        "--input",
        EXPORTS_DIR / "problematic",
        "--out",
        tmp_path,
    )

    output = capsys.readouterr().out
    manifest = json.loads((run_dirs(tmp_path)[0] / MANIFEST_NAME).read_text("utf-8"))
    assert code == cli.EXIT_OK
    assert "21 row(s) rejected, 7 kept with warnings, 1 excluded by profile" in output
    assert manifest["result"]["status"] == "completed_with_rejections"


def test_xlsx_exports_reconcile_like_csv_exports(tmp_path):
    """
    tests an end-to-end run where every export is an XLSX workbook
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    for path in (EXPORTS_DIR / "clean").glob("*.csv"):
        csv_to_xlsx(path, input_dir / path.with_suffix(".xlsx").name)

    code = run_cli(
        "run", "--profile", PROFILE_PATH, "--input", input_dir, "--out", tmp_path / "o"
    )

    assert code == cli.EXIT_OK
    assert ledger_from_csv(run_dirs(tmp_path / "o")[0]) == CLEAN_LEDGER


def test_mixed_csv_and_xlsx_exports(tmp_path):
    """
    tests one reporting period in CSV and the other in XLSX
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = copy_exports(
        "clean",
        tmp_path / "in",
        {"customers.csv", "orders_2026-08.csv", "payments_2026-08.csv"},
    )
    for name in ("orders_2026-09.csv", "payments_2026-09.csv"):
        csv_to_xlsx(
            EXPORTS_DIR / "clean" / name, input_dir / name.replace(".csv", ".xlsx")
        )

    code = run_cli(
        "run", "--profile", PROFILE_PATH, "--input", input_dir, "--out", tmp_path / "o"
    )

    assert code == cli.EXIT_OK
    assert ledger_from_csv(run_dirs(tmp_path / "o")[0]) == CLEAN_LEDGER


def test_repeated_cli_runs_never_overwrite_and_agree(tmp_path):
    """
    tests rerun behavior through the CLI
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    for _ in range(2):
        assert (
            run_cli(
                "run",
                "--profile",
                PROFILE_PATH,
                "--input",
                EXPORTS_DIR / "clean",
                "--out",
                tmp_path,
            )
            == cli.EXIT_OK
        )

    first, second = run_dirs(tmp_path)
    manifests = [
        json.loads((path / MANIFEST_NAME).read_text("utf-8"))
        for path in (first, second)
    ]
    assert manifests[0]["result"] == manifests[1]["result"]
    assert (first / LEDGER_NAME).read_bytes() == (second / LEDGER_NAME).read_bytes()


def test_invalid_profile_exits_with_usage_code(tmp_path, capsys):
    """
    tests that a broken profile fails before any data is read
    :param tmp_path: pytest temporary directory
    :param capsys: pytest output capture
    :returns: none
    """
    profile = tmp_path / "bad.toml"
    profile.write_text(
        PROFILE_PATH.read_text("utf-8").replace(
            '"Partially Paid" = "partial"', ('"Partially Paid" = "partly"')
        ),
        encoding="utf-8",
    )

    code = run_cli(
        "run", "--profile", profile, "--input", EXPORTS_DIR / "clean", "--out", tmp_path
    )

    error = capsys.readouterr().err
    assert code == cli.EXIT_USAGE
    assert "'partly' is not a supported status" in error
    assert run_dirs(tmp_path) == []


@pytest.mark.parametrize("setup", ["missing_dir", "missing_column", "no_payments"])
def test_input_problems_exit_with_input_code(tmp_path, capsys, setup):
    """
    tests structural input failures
    :param tmp_path: pytest temporary directory
    :param capsys: pytest output capture
    :param setup: kind of input problem to create
    :returns: none
    """
    input_dir = copy_exports("clean", tmp_path / "in")
    if setup == "missing_dir":
        input_dir = tmp_path / "absent"
    elif setup == "missing_column":
        path = input_dir / "payments_2026-08.csv"
        path.write_text(
            path.read_text("utf-8").replace("Transaction ID", "Txn"), "utf-8"
        )
    else:
        for path in input_dir.glob("payments*"):
            path.unlink()

    code = run_cli(
        "run", "--profile", PROFILE_PATH, "--input", input_dir, "--out", tmp_path / "o"
    )

    assert code == cli.EXIT_INPUT
    assert "input error" in capsys.readouterr().err
    assert run_dirs(tmp_path / "o") == []


@pytest.mark.parametrize("location", ["inside_input", "examples", "data"])
def test_unsafe_output_locations_are_refused(tmp_path, capsys, location):
    """
    tests that runs never write into input or tracked example directories
    :param tmp_path: pytest temporary directory
    :param capsys: pytest output capture
    :param location: output location to try
    :returns: none
    """
    input_dir = copy_exports("clean", tmp_path / "in")
    out_dir = {
        "inside_input": input_dir / "results",
        "examples": ROOT / "examples" / "ordixa" / "runs",
        "data": ROOT / "data" / "runs",
    }[location]

    code = run_cli(
        "run", "--profile", PROFILE_PATH, "--input", input_dir, "--out", out_dir
    )

    assert code == cli.EXIT_OUTPUT
    assert "output error" in capsys.readouterr().err
    assert not out_dir.exists()


def test_integrity_failure_writes_nothing(tmp_path, capsys, monkeypatch):
    """
    tests that a failed cross-check stops before outputs are written
    :param tmp_path: pytest temporary directory
    :param capsys: pytest output capture
    :param monkeypatch: pytest fixture for replacing the integrity check
    :returns: none
    """

    def fail(ledger, records):
        raise pipeline.ReconciliationIntegrityError("simulated mismatch")

    monkeypatch.setattr(pipeline, "verify_integrity", fail)

    code = run_cli(
        "run",
        "--profile",
        PROFILE_PATH,
        "--input",
        EXPORTS_DIR / "clean",
        "--out",
        tmp_path,
    )

    assert code == cli.EXIT_INTEGRITY
    assert "simulated mismatch" in capsys.readouterr().err
    assert run_dirs(tmp_path) == []


def test_check_profile_command(tmp_path, capsys):
    """
    tests the profile-only validation command
    :param tmp_path: pytest temporary directory
    :param capsys: pytest output capture
    :returns: none
    """
    assert run_cli("check-profile", "--profile", PROFILE_PATH) == cli.EXIT_OK
    assert "is valid" in capsys.readouterr().out
    assert run_cli("check-profile", "--profile", tmp_path / "x.toml") == cli.EXIT_USAGE


def test_missing_arguments_use_argparse_exit_code():
    """
    tests that incomplete commands fail with a usage error
    :returns: none
    """
    with pytest.raises(SystemExit) as error:
        cli.main(["run", "--profile", str(PROFILE_PATH)])

    assert error.value.code == cli.EXIT_USAGE


def test_module_entry_point_runs_as_a_subprocess(tmp_path):
    """
    tests the documented python -m app.ordixa invocation
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.ordixa",
            "run",
            "--profile",
            str(PROFILE_PATH),
            "--input",
            str(EXPORTS_DIR / "clean"),
            "--out",
            str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert completed.returncode == 0, completed.stderr
    assert "workbook:" in completed.stdout
    assert len(run_dirs(tmp_path)) == 1
