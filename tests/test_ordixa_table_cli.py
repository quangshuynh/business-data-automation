"""
tests for the clean, compare, and table-profile check-profile commands
"""

import json
import shutil

import pytest
from ordixa_helpers import PROFILE_PATH, ROOT, write_rows
from table_helpers import CLEAN_PROFILE, COMPARE_PROFILE, HEADER, INVENTORY_DIR

from app.ordixa import cli
from app.ordixa.manifest import MANIFEST_NAME
from app.ordixa.tabular import TabularIntegrityError
from app.ordixa.tabular_outputs import CLEANED_NAME, REPORT_NAME

BEFORE = INVENTORY_DIR / "inventory-before.csv"
AFTER = INVENTORY_DIR / "inventory-after.csv"
# a value that must never reach the terminal
SENTINEL = "Zebulon Quartzfield"


def run_cli(*args):
    """
    invokes the CLI entry point in-process
    :param args: command line arguments
    :returns: exit code
    """
    return cli.main([str(arg) for arg in args])


def run_dirs(out_dir):
    """
    lists published run directories
    :param out_dir: parent output directory
    :returns: sorted list of run directories
    """
    if not out_dir.exists():
        return []
    return sorted(p for p in out_dir.iterdir() if p.name.startswith("run-"))


def compare_args(out_dir, before=BEFORE, after=AFTER, profile=COMPARE_PROFILE):
    """
    builds compare command arguments
    :param out_dir: output directory
    :param before: earlier export
    :param after: later export
    :param profile: profile path
    :returns: argument list
    """
    return [
        "compare",
        "--profile",
        profile,
        "--before",
        before,
        "--after",
        after,
        "--out",
        out_dir,
    ]


def test_clean_command(tmp_path, capsys):
    """
    tests a clean run from the command line
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :returns: none
    """
    code = run_cli(
        "clean", "--profile", CLEAN_PROFILE, "--input", BEFORE, "--out", tmp_path
    )
    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    (run_dir,) = run_dirs(tmp_path)
    assert (run_dir / CLEANED_NAME).is_file()
    assert "120 row(s) written, 0 rejected, 1 exact duplicate(s) removed" in out
    assert "(completed)" in out


def test_compare_command_and_verify(tmp_path, capsys):
    """
    tests a compare run and its verification with inputs from two places
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :returns: none
    """
    week1, week2 = tmp_path / "week1", tmp_path / "week2"
    week1.mkdir()
    week2.mkdir()
    before = shutil.copy(BEFORE, week1 / "inventory.csv")
    after = shutil.copy(AFTER, week2 / "inventory.csv")

    assert run_cli(*compare_args(tmp_path / "out", before, after)) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "6 added, 4 removed, 19 modified, 94 unchanged" in out
    assert "1 ambiguous key(s), 2 invalid key(s), 1 rejected row(s)" in out
    (run_dir,) = run_dirs(tmp_path / "out")
    assert (run_dir / REPORT_NAME).is_file()

    code = run_cli("verify", "--run", run_dir, "--input", week1, "--input", week2)
    assert code == cli.EXIT_OK
    assert "all 12 checks passed" in capsys.readouterr().out

    assert run_cli("verify", "--run", run_dir, "--input", week1) == cli.EXIT_INTEGRITY
    assert run_cli("verify", "--run", run_dir, "--input", tmp_path / "nope") == (
        cli.EXIT_INPUT
    )


def test_terminal_output_never_shows_cell_values(tmp_path, capsys):
    """
    tests that progress and issue output carries counts and names only
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :returns: none
    """
    rows = [
        ["SKU-1", SENTINEL, "1.00", "1", ""],
        ["SKU-1", SENTINEL, "2.00", "1", ""],
        ["SKU-2", SENTINEL, "bad", "1", ""],
    ]
    before = write_rows(tmp_path / "in" / "before.csv", HEADER, rows)
    after = write_rows(tmp_path / "in" / "after.csv", HEADER, rows[::-1])
    profile = tmp_path / "p.toml"
    profile.write_text(
        COMPARE_PROFILE.read_text(encoding="utf-8")
        .replace('"Item SKU"', '"SKU"')
        .replace('"Product Name"', '"Name"')
        .replace('"Unit Price"', '"Price"')
        .replace('"Qty On Hand"', '"Qty"')
        .replace('"Last Counted"', '"Counted"')
        .replace('source = "Category"', 'source = "Category Name"')
        .replace('source = "Supplier"', 'source = "Supplier Name"'),
        encoding="utf-8",
    )
    assert run_cli(*compare_args(tmp_path / "out", before, after, profile)) == 0
    run_cli("check-profile", "--profile", profile, "--input", after)
    captured = capsys.readouterr()
    assert SENTINEL not in captured.out + captured.err
    assert "bad" not in captured.out + captured.err


def test_wrong_profile_kinds_are_usage_errors(tmp_path, capsys):
    """
    tests that each command refuses the other workflows' profiles
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :returns: none
    """
    assert run_cli(*compare_args(tmp_path, profile=CLEAN_PROFILE)) == cli.EXIT_USAGE
    code = run_cli(
        "clean", "--profile", PROFILE_PATH, "--input", BEFORE, "--out", tmp_path
    )
    assert code == cli.EXIT_USAGE
    code = run_cli(
        "run", "--profile", CLEAN_PROFILE, "--input", INVENTORY_DIR, "--out", tmp_path
    )
    assert code == cli.EXIT_USAGE
    err = capsys.readouterr().err
    assert "use python -m app.ordixa clean" in err
    assert "use python -m app.ordixa run" in err
    assert run_dirs(tmp_path) == []


def test_input_problems_exit_with_input_code(tmp_path, capsys):
    """
    tests missing files and missing required columns
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :returns: none
    """
    missing = run_cli(*compare_args(tmp_path / "o", after=tmp_path / "nope.csv"))
    assert missing == cli.EXIT_INPUT
    partial = write_rows(tmp_path / "in" / "items.csv", ["Item SKU"], [["SKU-1"]])
    code = run_cli(
        "clean", "--profile", CLEAN_PROFILE, "--input", partial, "--out", tmp_path / "o"
    )
    assert code == cli.EXIT_INPUT
    assert "missing required columns" in capsys.readouterr().err
    assert run_dirs(tmp_path / "o") == []


def test_output_inside_tracked_folders_is_refused(capsys):
    """
    tests the existing output-path safety for the new commands
    :param capsys: pytest capture fixture
    :returns: none
    """
    target = ROOT / "examples" / "ordixa" / "exports" / "inventory-out"
    assert run_cli(*compare_args(target)) == cli.EXIT_OUTPUT
    assert not target.exists()
    assert "inside the tracked examples/ directory" in capsys.readouterr().err


def test_sensitive_headers_are_flagged_by_name(tmp_path, capsys):
    """
    tests the header heuristic warnings; unmapped columns stay out of outputs
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :returns: none
    """
    header = ["Item SKU", "Product Name", "Unit Price", "Qty On Hand", "Card Number"]
    path = write_rows(
        tmp_path / "in" / "items.csv",
        header,
        [["SKU-1", "Mug", "1.00", "1", "4111111111111111"]],
    )
    code = run_cli(
        "clean", "--profile", CLEAN_PROFILE, "--input", path, "--out", tmp_path / "o"
    )
    assert code == cli.EXIT_OK
    err = capsys.readouterr().err
    assert "'Card Number' looks like card" in err and "left out of the outputs" in err
    (run_dir,) = run_dirs(tmp_path / "o")
    assert "4111" not in (run_dir / CLEANED_NAME).read_text(encoding="utf-8")


def test_check_profile_dry_run_for_table_profiles(capsys):
    """
    tests check-profile validation and its read-only dry run
    :param capsys: pytest capture fixture
    :returns: none
    """
    assert run_cli("check-profile", "--profile", COMPARE_PROFILE) == cli.EXIT_OK
    assert "inventory-compare 1.0.0 (compare) is valid" in capsys.readouterr().out

    code = run_cli(
        "check-profile", "--profile", CLEAN_PROFILE, "--input", AFTER, "--json"
    )
    assert code == cli.EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert report["rows_written"] == 119
    assert report["issues"] == {
        "conflicting_key": 2,
        "missing_value": 3,
        "unmapped_columns": 1,
    }


def test_integrity_and_unexpected_errors_publish_nothing(tmp_path, capsys, monkeypatch):
    """
    tests exit codes and withheld details for internal failures
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :param monkeypatch: pytest monkeypatch fixture
    :returns: none
    """

    def broken(*args):
        raise TabularIntegrityError("counts do not add up")

    monkeypatch.setattr(cli, "compare_tables", broken)
    assert run_cli(*compare_args(tmp_path)) == cli.EXIT_INTEGRITY

    def leaky(*args):
        raise ValueError(f"could not parse {SENTINEL}")

    monkeypatch.delenv("ORDIXA_DEBUG", raising=False)
    monkeypatch.setattr(cli, "compare_tables", leaky)
    assert run_cli(*compare_args(tmp_path)) == cli.EXIT_UNEXPECTED
    err = capsys.readouterr().err
    assert SENTINEL not in err and "details withheld" in err
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("command", ["clean", "compare"])
def test_help_lists_the_new_commands(command, capsys):
    """
    tests that the new subcommands are discoverable
    :param command: subcommand name
    :param capsys: pytest capture fixture
    :returns: none
    """
    with pytest.raises(SystemExit):
        run_cli("--help")
    assert command in capsys.readouterr().out


def test_manifest_records_both_inputs(tmp_path):
    """
    tests that a compare manifest records both files by role
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    run_cli(*compare_args(tmp_path))
    (run_dir,) = run_dirs(tmp_path)
    manifest = json.loads((run_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert [(i["role"], i["file"]) for i in manifest["result"]["inputs"]] == [
        ("before", "inventory-before.csv"),
        ("after", "inventory-after.csv"),
    ]
