"""
tests for the guided inventory clean/compare demo
"""

import json

from app.ordixa.cli import EXIT_INTEGRITY, EXIT_OK, EXIT_OUTPUT
from app.ordixa.inventory_demo import DEMO_INPUT, main
from app.ordixa.manifest import MANIFEST_NAME

# pinned so any change to cleaning, comparison, or artifact content is noticed;
# update only together with a WORKFLOW_VERSION bump or a deliberate fixture edit
INVENTORY_COMPARE_FINGERPRINT = (
    "ac5c90fd51c2b48a5d82213f0ce47f7b0c80d3da227aa55eff3101525af0060e"
)


def test_demo_cleans_compares_and_verifies(tmp_path, capsys):
    """
    tests the full demo against the fixture totals
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :returns: none
    """
    assert main(["--out", str(tmp_path)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "121 rows read, 120 written, 1 exact duplicate removed, 0 rejected" in out
    assert "6 added, 4 removed, 19 modified, 94 unchanged" in out
    assert "8 price changes, 10 stock changes" in out
    assert "FAIL" not in out and "Demo complete" in out

    (compare_dir,) = (tmp_path / "compare").iterdir()
    manifest = json.loads((compare_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["result"]["result_fingerprint"] == INVENTORY_COMPARE_FINGERPRINT
    assert len(list((tmp_path / "clean").iterdir())) == 1


def test_demo_refuses_tracked_output_folders(capsys):
    """
    tests that the demo applies the output-location rules
    :param capsys: pytest capture fixture
    :returns: none
    """
    assert main(["--out", str(DEMO_INPUT / "runs")]) == EXIT_OUTPUT
    assert not (DEMO_INPUT / "runs").exists()
    assert "output error" in capsys.readouterr().err


def test_demo_reports_failed_verification(tmp_path, capsys, monkeypatch):
    """
    tests that a failed verification check produces the integrity exit code
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :param monkeypatch: pytest monkeypatch fixture
    :returns: none
    """
    monkeypatch.setattr(
        "app.ordixa.inventory_demo.verify_run", lambda *args: [("forced check", False)]
    )
    assert main(["--out", str(tmp_path)]) == EXIT_INTEGRITY
    captured = capsys.readouterr()
    assert "FAIL forced check" in captured.out
    assert "verification failed" in captured.err
