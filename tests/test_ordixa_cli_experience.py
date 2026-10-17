"""
tests for command help, run summaries, and actionable error guidance
"""

import re
import shlex

import pytest
from ordixa_helpers import EXPORTS_DIR, PROFILE_PATH
from table_helpers import CLEAN_PROFILE, COMPARE_PROFILE, INVENTORY_DIR

from app.ordixa import cli

COMMANDS = ["inspect", "check-profile", "run", "clean", "compare", "verify"]
BEFORE = INVENTORY_DIR / "inventory-before.csv"
AFTER = INVENTORY_DIR / "inventory-after.csv"


def run_cli(*args):
    """
    invokes the CLI entry point in-process
    :param args: command line arguments
    :returns: exit code
    """
    return cli.main([str(arg) for arg in args])


def verify_command_from(output):
    """
    extracts the verify command a finished run printed
    :param output: captured standard output
    :returns: argument list after python -m app.ordixa
    """
    (line,) = [
        line for line in output.splitlines() if "verify before delivering" in line
    ]
    command = line.split("python -m app.ordixa ", 1)[1]
    return shlex.split(command.replace("\\", "/"))


@pytest.mark.parametrize("command", COMMANDS)
def test_every_command_help_has_examples(command, capsys):
    """
    tests that each subcommand's help ends with runnable examples
    :param command: subcommand name
    :param capsys: pytest capture fixture
    :returns: none
    """
    with pytest.raises(SystemExit) as stop:
        cli.main([command, "--help"])
    assert stop.value.code == 0
    out = capsys.readouterr().out
    assert "examples:" in out
    assert f"python -m app.ordixa {command}" in out


@pytest.mark.parametrize("command", COMMANDS)
def test_help_examples_parse_with_the_real_parser(command):
    """
    tests that every documented example is a valid command line
    :param command: subcommand name
    :returns: none
    """
    parser = cli.build_parser()
    text = cli.EXAMPLES[command].replace("\\\n", " ")
    examples = [line.strip() for line in text.splitlines()[1:] if line.strip()]
    assert examples
    for example in examples:
        argv = shlex.split(example)[3:]
        args = parser.parse_args(argv)
        assert args.command == command


def test_main_help_documents_every_exit_code(capsys):
    """
    tests the exit code table against the constants the CLI returns
    :param capsys: pytest capture fixture
    :returns: none
    """
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    documented = {int(code) for code in re.findall(r"^  (\d)  ", out, re.MULTILINE)}
    constants = {value for name, value in vars(cli).items() if name.startswith("EXIT_")}
    assert documented == constants
    assert "workflows:" in out


def test_run_summary_prints_a_working_verify_command(tmp_path, capsys):
    """
    tests that the printed verify command verifies the run it describes
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :returns: none
    """
    code = run_cli(
        "run",
        "--profile",
        PROFILE_PATH,
        "--input",
        EXPORTS_DIR / "problematic",
        "--out",
        tmp_path / "out",
    )
    assert code == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "run directory: " in out
    argv = verify_command_from(out)
    assert argv[0] == "verify" and argv.count("--input") == 1
    assert run_cli(*argv) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "all 11 checks passed" in out and "unchanged since the run" in out


def test_clean_summary_names_every_output(tmp_path, capsys):
    """
    tests the clean summary lines
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :returns: none
    """
    code = run_cli(
        "clean", "--profile", CLEAN_PROFILE, "--input", BEFORE, "--out", tmp_path / "o"
    )
    assert code == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "cleaned data: " in out and "held-back rows and reasons: " in out
    assert run_cli(*verify_command_from(out)) == cli.EXIT_OK


@pytest.mark.parametrize("same_folder", [True, False])
def test_compare_summary_verify_command_covers_both_inputs(
    tmp_path, capsys, same_folder
):
    """
    tests that the compare verify hint names one folder or both files
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :param same_folder: whether both exports sit in one directory
    :returns: none
    """
    before, after = BEFORE, AFTER
    if not same_folder:
        (tmp_path / "a").mkdir()
        after = tmp_path / "a" / AFTER.name
        after.write_bytes(AFTER.read_bytes())
    code = run_cli(
        "compare",
        "--profile",
        COMPARE_PROFILE,
        "--before",
        before,
        "--after",
        after,
        "--out",
        tmp_path / "o",
    )
    assert code == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "comparison INCOMPLETE" in out
    argv = verify_command_from(out)
    assert argv.count("--input") == (1 if same_folder else 2)
    assert run_cli(*argv) == cli.EXIT_OK


def test_input_errors_point_to_the_preflight(tmp_path, capsys):
    """
    tests the hint printed after an input error
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :returns: none
    """
    code = run_cli(
        "run",
        "--profile",
        PROFILE_PATH,
        "--input",
        EXPORTS_DIR / "pilot" / "1-first-delivery",
        "--out",
        tmp_path / "o",
    )
    assert code == cli.EXIT_INPUT
    err = capsys.readouterr().err
    assert "input error: no payments file found" in err
    assert "hint: check-profile --profile PROFILE --input DIR" in err
    assert not (tmp_path / "o").exists()


def test_missing_run_input_is_an_input_error_without_location_noise(tmp_path, capsys):
    """
    tests that a mistyped input directory gets one clear message
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :returns: none
    """
    code = run_cli(
        "run",
        "--profile",
        PROFILE_PATH,
        "--input",
        tmp_path / "missing",
        "--out",
        tmp_path / "o",
    )
    assert code == cli.EXIT_INPUT
    err = capsys.readouterr().err
    assert "input directory not found" in err
    assert "git-ignored" not in err


def test_verify_explains_what_run_expects(tmp_path, capsys):
    """
    tests the verify hint for a parent folder passed as --run
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :returns: none
    """
    assert run_cli("verify", "--run", tmp_path) == cli.EXIT_INPUT
    assert "one run-<id> directory" in capsys.readouterr().err


def test_verify_without_inputs_says_inputs_were_not_checked(tmp_path, capsys):
    """
    tests the verify guidance when --input is omitted
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :returns: none
    """
    run_cli("clean", "--profile", CLEAN_PROFILE, "--input", BEFORE, "--out", tmp_path)
    argv = verify_command_from(capsys.readouterr().out)
    assert run_cli(*argv[:3]) == cli.EXIT_OK
    assert "inputs were not checked" in capsys.readouterr().out
