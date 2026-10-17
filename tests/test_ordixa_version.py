"""
tests that the application reports one consistent version everywhere
"""

import re
import subprocess
import sys

import pytest
from ordixa_helpers import ROOT

from app.ordixa import __version__, cli
from app.ordixa.manifest import code_version, describe_version

RELEASE_VERSION = "2.0.0"


def test_version_is_the_release_version():
    """
    tests the single authoritative version constant
    :returns: none
    """
    assert __version__ == RELEASE_VERSION
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_cli_version_flag(capsys):
    """
    tests that --version prints the package version and exits cleanly
    :param capsys: pytest capture fixture
    :returns: none
    """
    with pytest.raises(SystemExit) as stop:
        cli.main(["--version"])
    assert stop.value.code == 0
    assert capsys.readouterr().out.strip() == f"ordixa {__version__}"


def test_module_version_flag_in_a_subprocess():
    """
    tests python -m app.ordixa --version exactly as documented
    :returns: none
    """
    completed = subprocess.run(
        [sys.executable, "-m", "app.ordixa", "--version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == f"ordixa {RELEASE_VERSION}"


def test_manifests_and_workbooks_use_the_same_version():
    """
    tests that run metadata reads the version from the same constant
    :returns: none
    """
    version = code_version()
    assert version["ordixa"] == __version__
    assert describe_version(version).startswith(__version__)


def test_no_other_module_defines_a_version():
    """
    tests that no second version constant can drift from __version__
    :returns: none
    """
    pattern = re.compile(r"^__version__\s*=", re.MULTILINE)
    defining = [
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "app").rglob("*.py")
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert defining == ["app/ordixa/__init__.py"]
