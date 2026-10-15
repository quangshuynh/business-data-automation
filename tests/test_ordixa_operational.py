"""
tests for operational safeguards around customer files, outputs, and logs
"""

import pytest
from ordixa_helpers import EXPORTS_DIR, PROFILE_PATH, ROOT

from app.ordixa import cli, pipeline


def run_cli(*args):
    """
    runs the command line entry point
    :param args: arguments
    :returns: exit code
    """
    return cli.main([str(arg) for arg in args])


def test_output_inside_the_repository_must_be_git_ignored(tmp_path, capsys):
    """
    a run directory in an unignored repository folder could be committed
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :returns: none
    """
    out_dir = ROOT / "ordixa-results-should-not-exist"

    code = run_cli(
        "run",
        "--profile",
        PROFILE_PATH,
        "--input",
        EXPORTS_DIR / "clean",
        "--out",
        out_dir,
    )

    assert code == cli.EXIT_OUTPUT
    assert "not in a git-ignored folder" in capsys.readouterr().err
    assert not out_dir.exists()


@pytest.mark.parametrize("folder", ["output", "customer-data"])
def test_ignored_repository_folders_are_allowed_for_output(tmp_path, folder):
    """
    output/ and customer-data/ are git-ignored and accepted
    :param tmp_path: pytest temporary directory
    :param folder: ignored folder name
    :returns: none
    """
    cli.check_output_location(ROOT / folder / "runs", tmp_path)


def test_docs_folder_is_protected(tmp_path):
    """
    docs/ is tracked and refused like the other source folders
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    with pytest.raises(OSError, match="tracked docs/"):
        cli.check_output_location(ROOT / "docs" / "runs", tmp_path)


def test_inputs_in_unignored_repository_folders_trigger_a_warning(capsys, tmp_path):
    """
    customer exports inside the repository are flagged; fixtures are not
    :param capsys: pytest capture fixture
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    cli.warn_about_input_location(ROOT / "exports")
    warned = capsys.readouterr().err
    cli.warn_about_input_location(EXPORTS_DIR / "clean")
    cli.warn_about_input_location(ROOT / "customer-data" / "acme")
    cli.warn_about_input_location(tmp_path)

    assert "inside the repository and not git-ignored" in warned
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("debug", [False, True])
def test_unexpected_errors_withhold_details_by_default(
    tmp_path, capsys, monkeypatch, debug
):
    """
    library error messages can quote row values, so they are only printed when
    ORDIXA_DEBUG is set
    :param tmp_path: pytest temporary directory
    :param capsys: pytest capture fixture
    :param monkeypatch: pytest monkeypatch fixture
    :param debug: whether ORDIXA_DEBUG is set
    :returns: none
    """

    def explode(*_args):
        raise ValueError("could not convert 'Avery Quinn <a@example.com>'")

    monkeypatch.setattr(cli, "process", explode)
    monkeypatch.setattr(pipeline, "process", explode)
    if debug:
        monkeypatch.setenv("ORDIXA_DEBUG", "1")
    else:
        monkeypatch.delenv("ORDIXA_DEBUG", raising=False)

    code = run_cli(
        "run",
        "--profile",
        PROFILE_PATH,
        "--input",
        EXPORTS_DIR / "clean",
        "--out",
        tmp_path / "out",
    )
    err = capsys.readouterr().err

    assert code == cli.EXIT_UNEXPECTED
    assert "ValueError" in err
    assert ("Avery Quinn" in err) is debug
    assert "no run directory was kept" in err
    assert not (tmp_path / "out").exists()


def test_customer_data_folder_is_ignored_by_git_and_docker():
    """
    the conventional customer-data/ folder never reaches a commit or image
    :returns: none
    """
    gitignore = (ROOT / ".gitignore").read_text("utf-8").splitlines()
    dockerignore = (ROOT / ".dockerignore").read_text("utf-8").splitlines()

    assert "customer-data/" in gitignore
    assert "customer-data" in dockerignore
    assert "output/*" in gitignore
