import json
import shutil

import pytest
from ordixa_helpers import (
    EXPORTS_DIR,
    ORDER_HEADER,
    PAYMENT_HEADER,
    PROFILE_PATH,
    TEXT_ID_PROFILE_PATH,
    build_profile,
    csv_to_xlsx,
    write_exports,
    write_rows,
)

from app.ordixa import cli
from app.ordixa.adapters import discover_inputs
from app.ordixa.issues import InputError
from app.ordixa.preflight import preflight
from app.ordixa.profile import load_profile

PILOT_DIR = EXPORTS_DIR / "pilot"


def codes(report, level=None):
    """
    lists finding codes in a preflight report
    :param report: preflight report
    :param level: optional level filter
    :returns: list of codes
    """
    return [
        item["code"]
        for item in report["findings"]
        if level is None or item["level"] == level
    ]


def snapshot(directory):
    """
    records every file under a directory with its bytes
    :param directory: directory to snapshot
    :returns: mapping of relative path to bytes
    """
    return {
        str(path.relative_to(directory)): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def test_missing_dataset_and_unused_personal_column_are_reported_together():
    """
    tests that one preflight reports every structural problem at once
    :returns: none
    """
    report = preflight(build_profile(), PILOT_DIR / "1-first-delivery")

    assert report["readiness"] == "blocked"
    assert codes(report, "blocking") == ["missing_dataset"]
    personal = [
        item for item in report["findings"] if item["code"] == "unused_personal_column"
    ]
    assert len(personal) == 1
    assert "'Shipping Address'" in personal[0]["message"]
    assert report["rows"] is None
    assert report["datasets"]["payments"]["files"] == []


def test_changed_header_names_the_closest_column():
    """
    tests that a renamed source column blocks with the nearest header named
    :returns: none
    """
    report = preflight(build_profile(), PILOT_DIR / "2-second-delivery")

    assert report["readiness"] == "blocked"
    [missing] = [i for i in report["findings"] if i["code"] == "missing_column"]
    assert "'Order Reference' (found 'Order Ref')" in missing["message"]


def test_final_delivery_reports_row_outcomes_and_unmatched_payments():
    """
    tests the in-memory row checks on the processable pilot batch
    :returns: none
    """
    report = preflight(build_profile(), PILOT_DIR / "3-final-delivery")

    assert report["readiness"] == "review"
    assert codes(report) == ["order_not_in_run"]
    rows = report["rows"]
    assert rows["counts"]["payments"]["rejected"] == 2
    assert rows["counts"]["orders"]["accepted"] == 6
    assert rows["status_counts"] == {
        "paid": 2,
        "partial": 2,
        "unpaid": 2,
        "overpaid": 0,
    }
    assert rows["issues"] == [
        {
            "dataset": "payments",
            "severity": "error",
            "code": "order_not_in_run",
            "field": "order_id",
            "rows": 2,
        }
    ]


def test_clean_text_identifier_batch_is_ready():
    """
    tests that a batch with only row warnings is ready
    :returns: none
    """
    report = preflight(load_profile(TEXT_ID_PROFILE_PATH), EXPORTS_DIR / "text-ids")

    assert report["readiness"] == "ready"
    assert report["findings"] == []


def test_prohibited_column_blocks_without_printing_values(tmp_path, capsys):
    """
    tests that card-like columns block and their cells are never printed
    :param tmp_path: pytest temporary directory
    :param capsys: pytest output capture
    :returns: none
    """
    write_exports(
        tmp_path,
        orders=[["#1", "2026-11-02", "", "USD", "10.00"]],
        payments=[["PMT-1", "#1", "11/02/2026", "Payment", "Paid", "10.00", "USD"]],
    )
    write_rows(
        tmp_path / "payments.csv",
        [*PAYMENT_HEADER, "Card Number"],
        [
            [
                "PMT-1",
                "#1",
                "11/02/2026",
                "Payment",
                "Paid",
                "10.00",
                "USD",
                "4000 0000 0000 0002",
            ]
        ],
    )

    exit_code = cli.main(
        ["check-profile", "--profile", str(PROFILE_PATH), "--input", str(tmp_path)]
    )
    output = capsys.readouterr().out

    assert exit_code == cli.EXIT_INPUT
    assert "prohibited_column" in output
    assert "'Card Number'" in output
    assert "4000" not in output
    assert "skipped until blocking findings are resolved" in output


def test_report_contains_no_cell_values(capsys):
    """
    tests that text and JSON preflight output never include names or emails
    :param capsys: pytest output capture
    :returns: none
    """
    demo = EXPORTS_DIR / "demo"
    for extra in ([], ["--json"]):
        cli.main(
            ["check-profile", "--profile", str(PROFILE_PATH), "--input", str(demo)]
            + extra
        )
        output = capsys.readouterr().out
        for value in ("Castellanos", "example.com", "555-010", "1O5.00", "Disputed"):
            assert value not in output


def test_preflight_writes_nothing(tmp_path):
    """
    tests that preflight leaves the input directory byte-for-byte unchanged
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    batch = tmp_path / "batch"
    shutil.copytree(PILOT_DIR / "3-final-delivery", batch)
    before = snapshot(tmp_path)

    preflight(build_profile(), batch)

    assert snapshot(tmp_path) == before


def test_unsupported_and_unclaimed_files_are_flagged(tmp_path):
    """
    tests that files no dataset reads are reported instead of silently skipped
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    shutil.copytree(PILOT_DIR / "3-final-delivery", tmp_path, dirs_exist_ok=True)
    (tmp_path / "refunds_2026-11.xls").write_bytes(b"legacy")
    (tmp_path / "settlements.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    report = preflight(build_profile(), tmp_path)

    by_code = {item["code"]: item["message"] for item in report["findings"]}
    assert "legacy Excel" in by_code["unsupported_file"]
    assert by_code["ignored_file"].startswith("settlements.csv")
    assert report["rows"] is not None


def test_missing_input_directory_is_blocking(tmp_path):
    """
    tests that a nonexistent batch directory is reported as blocked
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    report = preflight(build_profile(), tmp_path / "absent")

    assert report["readiness"] == "blocked"
    assert codes(report) == ["input_error"]


def test_header_only_orders_file_is_blocking(tmp_path):
    """
    tests that an orders export without data rows blocks the batch
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    write_rows(tmp_path / "orders.csv", ORDER_HEADER, [])
    write_rows(tmp_path / "payments.csv", PAYMENT_HEADER, [])

    report = preflight(build_profile(), tmp_path)

    assert report["readiness"] == "blocked"
    assert "no_rows" in codes(report, "blocking")


def test_unreadable_format_rejections_raise_a_profile_warning(tmp_path):
    """
    tests that many unparseable dates suggest a profile mismatch
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    write_exports(
        tmp_path,
        orders=[
            ["#1", "02/11/2026", "", "USD", "10.00"],
            ["#2", "03/11/2026", "", "USD", "12.00"],
        ],
        payments=[],
    )

    report = preflight(build_profile(), tmp_path)

    assert "high_rejection_rate" in codes(report, "warning")
    assert report["rows"]["issues"][0]["code"] == "invalid_date"
    assert report["rows"]["issues"][0]["rows"] == 2


def test_missing_worksheet_is_blocking(tmp_path):
    """
    tests that a profile naming an absent worksheet blocks the file
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    write_exports(
        tmp_path, orders=[["#1", "2026-11-02", "", "USD", "10.00"]], payments=[]
    )
    csv_to_xlsx(tmp_path / "payments.csv", tmp_path / "payments.xlsx", "Sheet1")
    (tmp_path / "payments.csv").unlink()

    def mutate(document):
        document["datasets"]["payments"]["sheet"] = "Transactions"

    report = preflight(build_profile(mutate), tmp_path)

    assert codes(report, "blocking") == ["missing_worksheet"]


def test_check_profile_without_input_is_unchanged(capsys):
    """
    tests that check-profile alone still only validates the profile
    :param capsys: pytest output capture
    :returns: none
    """
    assert cli.main(["check-profile", "--profile", str(PROFILE_PATH)]) == cli.EXIT_OK
    assert capsys.readouterr().out == "ordixa: profile harbor-lane 1.0.0 is valid\n"
    assert (
        cli.main(["check-profile", "--profile", str(PROFILE_PATH), "--json"])
        == cli.EXIT_USAGE
    )


def test_json_report_is_machine_readable(capsys):
    """
    tests the JSON preflight output shape
    :param capsys: pytest output capture
    :returns: none
    """
    exit_code = cli.main(
        [
            "check-profile",
            "--profile",
            str(PROFILE_PATH),
            "--input",
            str(PILOT_DIR / "3-final-delivery"),
            "--json",
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert exit_code == cli.EXIT_OK
    assert report["readiness"] == "review"
    assert report["profile"] == {"name": "harbor-lane", "version": "1.0.0"}


def test_run_discovery_still_fails_fast():
    """
    tests that discovery for real runs keeps stopping with the first problem
    :returns: none
    """
    with pytest.raises(InputError, match="no payments file found"):
        discover_inputs(PILOT_DIR / "1-first-delivery", build_profile())

    discovered, ignored = discover_inputs(
        PILOT_DIR / "2-second-delivery", build_profile()
    )
    assert [path.name for path in discovered["payments"]] == ["payments_2026-11.csv"]
    assert ignored == []


def test_verify_command_passes_and_detects_tampering(tmp_path, capsys):
    """
    tests the verify subcommand against a fresh and a modified run directory
    :param tmp_path: pytest temporary directory
    :param capsys: pytest output capture
    :returns: none
    """
    batch = PILOT_DIR / "3-final-delivery"
    out = tmp_path / "runs"
    assert (
        cli.main(
            [
                "run",
                "--profile",
                str(PROFILE_PATH),
                "--input",
                str(batch),
                "--out",
                str(out),
            ]
        )
        == cli.EXIT_OK
    )
    [run_dir] = list(out.iterdir())
    capsys.readouterr()

    args = ["verify", "--run", str(run_dir), "--input", str(batch)]
    assert cli.main(args) == cli.EXIT_OK
    assert "all 9 checks passed" in capsys.readouterr().out

    ledger = run_dir / "reconciliation_ledger.csv"
    ledger.write_bytes(ledger.read_bytes().replace(b"1075.00", b"1057.00"))
    assert cli.main(args) == cli.EXIT_INTEGRITY
    output = capsys.readouterr().out
    assert "FAIL reconciliation_ledger.csv matches its recorded SHA-256" in output
    assert "do not deliver this run" in output


def test_verify_command_refuses_a_directory_without_manifest(tmp_path, capsys):
    """
    tests that verify reports a missing manifest as an input problem
    :param tmp_path: pytest temporary directory
    :param capsys: pytest output capture
    :returns: none
    """
    assert cli.main(["verify", "--run", str(tmp_path)]) == cli.EXIT_INPUT
    assert "manifest.json does not exist" in capsys.readouterr().err
