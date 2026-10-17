"""
tests for the release gate script and the repository state it guards
"""

import pytest

from app.ordixa import __version__
from scripts import release_check


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    """
    points the release checks at a scratch repository root
    :param tmp_path: pytest temporary directory
    :param monkeypatch: pytest monkeypatch fixture
    :returns: scratch root path
    """
    monkeypatch.setattr(release_check, "ROOT", tmp_path)
    return tmp_path


def write(root, name, text):
    """
    writes a text file under the scratch root
    :param root: scratch root
    :param name: relative path
    :param text: file content
    :returns: relative path
    """
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return name


def test_slugs_follow_github_anchor_rules():
    """
    tests heading anchors used by documentation links
    :returns: none
    """
    assert release_check.slug("Quick start") == "quick-start"
    assert release_check.slug("`check-profile --explain`") == "check-profile---explain"
    assert release_check.slug("Security & data handling") == "security--data-handling"
    assert release_check.slug("v2.0.0 - 2026") == "v200---2026"


def test_broken_links_and_anchors_are_reported(fake_repo):
    """
    tests missing files, missing anchors, and ignored external links
    :param fake_repo: scratch root
    :returns: none
    """
    files = [
        write(fake_repo, "README.md", "# Title\n\n## Quick start\n"),
        write(
            fake_repo,
            "docs/GUIDE.md",
            "[ok](../README.md#quick-start) [web](https://example.com)\n"
            "[gone](MISSING.md) [anchor](../README.md#nope) [self](#local)\n"
            "```\n[ignored](NOPE.md)\n```\n## Local\n",
        ),
    ]
    problems = release_check.check_links(files)
    assert problems == [
        "docs/GUIDE.md:2: MISSING.md is not a tracked file",
        "docs/GUIDE.md:2: no heading for #nope",
    ]


def test_documented_commands_must_parse(fake_repo):
    """
    tests that a wrong option in a documented command is caught
    :param fake_repo: scratch root
    :returns: none
    """
    files = [
        write(
            fake_repo,
            "README.md",
            "```bash\n"
            "python -m app.ordixa clean --profile p.toml \\\n"
            "    --input a.csv --out output/x\n"
            "python -m app.ordixa compare --profile p.toml --input a.csv\n"
            "python -m app.ordixa --version\n"
            "```\n",
        )
    ]
    commands = release_check.documented_commands(files)
    assert [c for _, c in commands][0].endswith("--input a.csv --out output/x")
    (problem,) = release_check.check_commands(files)
    assert problem.startswith("README.md:4: does not parse")


def test_secrets_customer_files_and_stray_data_are_refused(fake_repo):
    """
    tests the tracked-file checks with planted problems
    :param fake_repo: scratch root
    :returns: none
    """
    token = "ghp_" + "a" * 36
    # assembled at run time so no tracked file holds a real-looking address
    real_domain = "mail-provider" + ".com"
    files = [
        write(fake_repo, ".env", "X=1\n"),
        write(fake_repo, "customer-data/acme/orders.csv", "id\n1\n"),
        write(fake_repo, "output/run-1/manifest.json", "{}\n"),
        write(fake_repo, "notes/export.csv", "id\n1\n"),
        write(fake_repo, "app/config.py", f"TOKEN = '{token}'\n"),
        write(fake_repo, "examples/people.csv", f"email\nreal.person@{real_domain}\n"),
        write(fake_repo, "examples/ok.csv", "email\na@example.com\nb@example.org\n"),
        write(fake_repo, "output/.gitkeep", ""),
    ]
    problems = release_check.check_tracked_files(files)
    assert any(p.startswith(".env:") for p in problems)
    assert any(p.startswith("customer-data/") for p in problems)
    assert any(p.startswith("output/run-1/") for p in problems)
    assert any("notes/export.csv: spreadsheet data outside" in p for p in problems)
    assert any(
        "app/config.py: looks like it contains a GitHub token" in p for p in problems
    )
    assert any(f"{real_domain} is not a reserved example domain" in p for p in problems)
    assert not any(
        p.startswith(("examples/ok.csv", "output/.gitkeep")) for p in problems
    )


def test_tag_must_match_the_version():
    """
    tests the version and tag consistency check
    :returns: none
    """
    assert release_check.check_version(f"v{__version__}") == []
    (problem,) = release_check.check_version("v9.9.9")
    assert "does not match" in problem


def test_this_repository_passes_every_release_check():
    """
    tests the real repository: version, changelog, links, commands, files
    :returns: none
    """
    results = dict(release_check.run_checks(f"v{__version__}"))
    assert results == {name: [] for name in results}
    assert len(release_check.documented_commands(release_check.tracked_files())) > 20
