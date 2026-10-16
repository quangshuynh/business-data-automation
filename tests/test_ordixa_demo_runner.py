"""
tests for the guided demo command and run verification
"""

import shutil

from ordixa_helpers import EXPORTS_DIR, build_profile

from app.ordixa.cli import EXIT_INTEGRITY, EXIT_OK, EXIT_OUTPUT
from app.ordixa.demo import main
from app.ordixa.manifest import LEDGER_NAME, verify_run, write_run_outputs
from app.ordixa.pipeline import process


def test_demo_runs_every_step_and_verifies(tmp_path, capsys):
    """
    tests that the demo walks through all seven steps and passes verification
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :returns: none
    """
    code = main(["--out", str(tmp_path)])
    out = capsys.readouterr().out

    assert code == EXIT_OK
    for number in range(1, 8):
        assert f"[{number}/7]" in out
    assert "15 orders reconciled: 9 paid, 3 partial, 2 unpaid, 1 overpaid" in out
    assert "net received 4063.65 USD; outstanding 922.75 USD" in out
    assert "FAIL" not in out
    assert out.count("  ok   ") == 9
    assert len(list(tmp_path.glob("run-*"))) == 1


def test_demo_output_contains_no_personal_data(tmp_path, capsys):
    """
    tests that names and email addresses from the exports are never printed
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :returns: none
    """
    main(["--out", str(tmp_path)])
    out = capsys.readouterr().out

    assert "@example" not in out
    assert "Castellanos" not in out


def test_demo_refuses_tracked_output_location(capsys):
    """
    tests that the demo never writes into tracked repository folders
    :param capsys: pytest capture fixture
    :returns: none
    """
    code = main(["--out", str(EXPORTS_DIR / "demo-out"), "--skip-inspect"])

    assert code == EXIT_OUTPUT
    assert "output error" in capsys.readouterr().err
    assert not (EXPORTS_DIR / "demo-out").exists()


def test_verify_run_detects_changed_outputs_and_inputs(tmp_path):
    """
    tests that verification fails when an artifact or an input changes
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = shutil.copytree(EXPORTS_DIR / "demo", tmp_path / "in")
    run_dir, _ = write_run_outputs(
        process(build_profile(), input_dir), tmp_path / "out"
    )
    assert all(passed for _, passed in verify_run(run_dir, input_dir))

    with (run_dir / LEDGER_NAME).open("a", encoding="utf-8") as handle:
        handle.write("#9999,tampered\n")
    (input_dir / "orders_2026-10.csv").write_text("changed", encoding="utf-8")

    failed = [name for name, passed in verify_run(run_dir, input_dir) if not passed]
    assert failed == [
        f"{LEDGER_NAME} matches its recorded SHA-256 and size",
        f"{LEDGER_NAME} has the recorded 15 data rows",
        "input orders_2026-10.csv is unchanged since the run",
    ]


def test_demo_reports_failed_verification(tmp_path, capsys, monkeypatch):
    """
    tests that a failed verification check produces the integrity exit code
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :param monkeypatch: pytest monkeypatch fixture
    :returns: none
    """
    monkeypatch.setattr(
        "app.ordixa.demo.verify_run", lambda *args: [("forced check", False)]
    )

    assert main(["--out", str(tmp_path), "--skip-inspect"]) == EXIT_INTEGRITY
    captured = capsys.readouterr()
    assert "FAIL forced check" in captured.out
    assert "verification failed" in captured.err
