"""
end-to-end and backward-compatibility tests for the Ordixa command line
"""

import json
import subprocess
import sys
from decimal import Decimal

import pytest
from ordixa_golden import TEXT_ID_LEDGER, TEXT_ID_TOTALS
from ordixa_helpers import (
    EXPORTS_DIR,
    PROFILE_PATH,
    ROOT,
    TEXT_ID_PROFILE_PATH,
    build_profile,
    csv_to_xlsx,
)

from app.ordixa.manifest import LEDGER_NAME, MANIFEST_NAME, result_fingerprint
from app.ordixa.pipeline import process

# result fingerprints produced by the Phase 1A release (a5ef7a9) for the
# fictional fixtures; numeric-identifier profiles must keep producing them
PHASE_1A_FINGERPRINTS = {
    "clean": "fe2f9187bbab94d605bb331d09e8a1bed22d1e3db54fef64f0b4490c3c3a25f1",
    "problematic": "be006fa316ab036b93bfa7e51f56bbecb4ee64b496db888ff0d78f343aa8bbeb",
}


def module(*args):
    """
    runs python -m app.ordixa in a subprocess from the repository root
    :param args: command line arguments
    :returns: completed process
    """
    return subprocess.run(
        [sys.executable, "-m", "app.ordixa", *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )


def only_run_dir(out_dir):
    """
    finds the single run directory written under a parent directory
    :param out_dir: parent output directory
    :returns: run directory path
    """
    (run_dir,) = [path for path in out_dir.iterdir()]
    assert run_dir.name.startswith("run-")
    return run_dir


@pytest.mark.parametrize("fixture_set", sorted(PHASE_1A_FINGERPRINTS))
def test_phase_1a_profiles_produce_phase_1a_results(fixture_set):
    """
    backward compatibility: the Harbor Lane profile without an identifiers table
    yields the same business result as Phase 1A
    :param fixture_set: clean or problematic
    :returns: none
    """
    result = process(build_profile(), EXPORTS_DIR / fixture_set)

    assert result_fingerprint(result) == PHASE_1A_FINGERPRINTS[fixture_set]


def test_inspect_then_run_text_identifier_exports(tmp_path):
    """
    the onboarding path works end to end in a subprocess: inspect the exports,
    validate the profile, then run and compare with hand-computed totals
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    inspected = module("inspect", "--input", EXPORTS_DIR / "text-ids", "--json")
    checked = module("check-profile", "--profile", TEXT_ID_PROFILE_PATH)
    ran = module(
        "run",
        "--profile",
        TEXT_ID_PROFILE_PATH,
        "--input",
        EXPORTS_DIR / "text-ids",
        "--out",
        tmp_path,
    )

    assert inspected.returncode == 0, inspected.stderr
    assert len(json.loads(inspected.stdout)["files"]) == 3
    assert checked.returncode == 0, checked.stderr
    assert ran.returncode == 0, ran.stderr
    assert "5 orders reconciled: 2 paid, 2 partial, 0 unpaid, 1 overpaid" in ran.stdout
    manifest = json.loads((only_run_dir(tmp_path) / MANIFEST_NAME).read_text("utf-8"))
    totals = manifest["result"]["totals"]
    for key, expected in TEXT_ID_TOTALS.items():
        assert Decimal(totals[key]) == expected, key


def test_text_identifier_xlsx_exports_run_from_the_cli(tmp_path):
    """
    the same exports saved as XLSX reconcile to the same ledger
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    for path in (EXPORTS_DIR / "text-ids").glob("*.csv"):
        csv_to_xlsx(path, input_dir / f"{path.stem}.xlsx")

    ran = module(
        "run",
        "--profile",
        TEXT_ID_PROFILE_PATH,
        "--input",
        input_dir,
        "--out",
        tmp_path / "out",
    )
    ledger = (only_run_dir(tmp_path / "out") / LEDGER_NAME).read_text("utf-8")

    assert ran.returncode == 0, ran.stderr
    for order_id in TEXT_ID_LEDGER:
        assert f"\n{order_id}," in ledger
    assert ",00012345," in ledger


def test_cli_rejects_unknown_identifier_mode(tmp_path):
    """
    a profile with an invalid identifier mode stops before reading data
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    profile = tmp_path / "bad.toml"
    profile.write_text(
        PROFILE_PATH.read_text("utf-8").replace(
            "[reconciliation]",
            '[identifiers]\norder_id = "alphanumeric"\n\n[reconciliation]',
        ),
        encoding="utf-8",
    )

    checked = module("check-profile", "--profile", profile)

    assert checked.returncode == 2
    assert "identifiers.order_id: must be one of ['numeric', 'text']" in checked.stderr
