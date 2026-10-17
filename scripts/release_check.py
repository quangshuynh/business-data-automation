"""
release gate checks that do not need a run: version, changelog, documentation,
documented commands, and tracked files

part of the release process in docs/RELEASING.md and run by CI on every push.
read-only; prints one ok/FAIL line per check and exits 1 when any fails

run from the repository root with:
    python -m scripts.release_check
    python -m scripts.release_check --tag v2.0.0
"""

import argparse
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ordixa import __version__  # noqa: E402
from app.ordixa.cli import build_parser  # noqa: E402

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)|!\[[^\]]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
CLI_PREFIX = "python -m app.ordixa "
# spreadsheet data may only live with the fictional examples and tests
DATA_SUFFIXES = {".csv", ".xlsx", ".xls", ".tsv"}
DATA_DIRS = ("examples/", "data/", "tests/")
MAX_TRACKED_BYTES = 5 * 1024 * 1024
# reserved documentation domains (RFC 2606) used by every fictional export,
# the same rule as the pilot's tracked-file test
FICTIONAL_DOMAINS = re.compile(r"^example\.(com|org|net)$", re.I)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
SECRETS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_\w{40,})"),
    "Slack token": re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    "Stripe live key": re.compile(r"\b[sr]k_live_[A-Za-z0-9]{16,}"),
    "Anthropic or OpenAI key": re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{32,}"),
}
FORBIDDEN_PATHS = (
    re.compile(r"(^|/)\.env$"),
    re.compile(r"^customer-data/"),
    re.compile(r"^output/(?!\.gitkeep$)"),
    re.compile(r"(^|/)\.run-[^/]*\.partial/"),
)


def tracked_files():
    """
    lists files tracked by git
    :returns: list of repository-relative POSIX paths
    """
    listing = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    return [name for name in listing.split("\0") if name]


def markdown_files(files):
    """
    selects tracked Markdown documents
    :param files: tracked paths
    :returns: list of paths
    """
    return [name for name in files if name.endswith(".md")]


def slug(heading):
    """
    builds the GitHub anchor for a Markdown heading
    :param heading: heading text
    :returns: anchor without the leading #
    """
    text = re.sub(r"`|\*\*|__|\[([^\]]*)\]\([^)]*\)", r"\1", heading).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path):
    """
    lists the heading anchors of a Markdown file
    :param path: Markdown file
    :returns: set of anchors
    """
    seen = {}
    result = set()
    fenced = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if FENCE.match(line):
            fenced = not fenced
            continue
        match = None if fenced else HEADING.match(line)
        if not match:
            continue
        base = slug(match.group(2))
        count = seen.get(base, 0)
        seen[base] = count + 1
        result.add(base if count == 0 else f"{base}-{count}")
    return result


def links(path):
    """
    lists the link targets of a Markdown file outside code blocks
    :param path: Markdown file
    :returns: list of (line number, target)
    """
    found = []
    fenced = False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        line = re.sub(r"`[^`]*`", "", line)
        for match in LINK.finditer(line):
            found.append((number, match.group(1) or match.group(2)))
    return found


def check_links(files):
    """
    checks that relative links and anchors in tracked Markdown resolve
    :param files: tracked paths
    :returns: list of problems
    """
    problems = []
    tracked = set(files)
    for name in markdown_files(files):
        source = ROOT / name
        for number, target in links(source):
            if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):
                continue
            path_part, _, anchor = target.partition("#")
            if path_part:
                resolved = (source.parent / path_part).resolve()
                try:
                    relative = resolved.relative_to(ROOT).as_posix()
                except ValueError:
                    problems.append(f"{name}:{number}: {target} leaves the repository")
                    continue
                is_dir = any(item.startswith(relative + "/") for item in tracked)
                if relative not in tracked and not is_dir:
                    problems.append(f"{name}:{number}: {target} is not a tracked file")
                    continue
            else:
                resolved = source
            if anchor and resolved.suffix == ".md" and anchor not in anchors(resolved):
                problems.append(f"{name}:{number}: no heading for #{anchor}")
    return problems


def documented_commands(files):
    """
    collects python -m app.ordixa commands from Markdown code blocks
    :param files: tracked paths
    :returns: list of (location, command text)
    """
    commands = []
    for name in markdown_files(files):
        lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
        fenced = False
        pending = None
        for number, line in enumerate(lines, 1):
            if FENCE.match(line):
                fenced = not fenced
                continue
            if not fenced:
                continue
            text = line.strip()
            if pending is not None:
                pending[1] += " " + text.rstrip("\\").strip()
                if not text.endswith("\\"):
                    commands.append(tuple(pending))
                    pending = None
                continue
            if text.startswith(CLI_PREFIX):
                entry = [f"{name}:{number}", text.rstrip("\\").strip()]
                if text.endswith("\\"):
                    pending = entry
                else:
                    commands.append(tuple(entry))
    return commands


def check_commands(files):
    """
    checks that every documented CLI command parses with the real parser
    :param files: tracked paths
    :returns: list of problems
    """
    problems = []
    parser = build_parser()
    for location, command in documented_commands(files):
        argv = shlex.split(command.split("#", 1)[0])[3:]
        if argv in (["--version"], ["--help"], ["-h"]) or "--help" in argv:
            continue
        try:
            parser.parse_args(argv)
        except SystemExit:
            problems.append(f"{location}: does not parse: {command}")
    return problems


def check_tracked_files(files):
    """
    checks for secrets, customer data, run outputs, and stray spreadsheets
    :param files: tracked paths
    :returns: list of problems
    """
    problems = []
    for name in files:
        if any(pattern.search(name) for pattern in FORBIDDEN_PATHS):
            problems.append(f"{name}: must never be committed")
        path = ROOT / name
        if not path.is_file():
            continue
        if path.stat().st_size > MAX_TRACKED_BYTES:
            problems.append(f"{name}: larger than {MAX_TRACKED_BYTES // 2**20} MB")
        suffix = path.suffix.lower()
        if suffix in DATA_SUFFIXES and not name.startswith(DATA_DIRS):
            problems.append(f"{name}: spreadsheet data outside {', '.join(DATA_DIRS)}")
        if suffix in {".png", ".xlsx", ".ico", ".jpg", ".gif", ".pdf"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in SECRETS.items():
            if pattern.search(text):
                problems.append(f"{name}: looks like it contains a {label}")
        if suffix in DATA_SUFFIXES:
            for domain in sorted({m.group(1) for m in EMAIL.finditer(text)}):
                if not FICTIONAL_DOMAINS.search(domain):
                    problems.append(
                        f"{name}: email domain {domain} is not a reserved example "
                        "domain; fictional data must use example.com/.org/.net"
                    )
    return problems


def check_version(tag):
    """
    checks the version constant, and the release tag when one is given
    :param tag: tag name such as v2.0.0, or none
    :returns: list of problems
    """
    problems = []
    if not SEMVER.match(__version__):
        problems.append(f"__version__ {__version__!r} is not MAJOR.MINOR.PATCH")
    if tag is not None and tag != f"v{__version__}":
        problems.append(f"tag {tag} does not match __version__ {__version__}")
    completed = subprocess.run(
        [sys.executable, "-m", "app.ordixa", "--version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.stdout.strip() != f"ordixa {__version__}":
        problems.append(f"--version printed {completed.stdout.strip()!r}")
    return problems


def check_release_notes():
    """
    checks that the changelog and, for 2.x, the migration guide cover the version
    :returns: list of problems
    """
    problems = []
    changelog = ROOT / "CHANGELOG.md"
    if not changelog.is_file():
        return ["CHANGELOG.md is missing"]
    text = changelog.read_text(encoding="utf-8")
    if not re.search(
        rf"^## \[{re.escape(__version__)}\] - \d{{4}}-\d{{2}}-\d{{2}}$", text, re.M
    ):
        problems.append(f"CHANGELOG.md has no dated '## [{__version__}]' section")
    if f"[{__version__}]: " not in text:
        problems.append(f"CHANGELOG.md has no link definition for [{__version__}]")
    major = int(__version__.split(".")[0])
    if major >= 2 and not (ROOT / "docs" / "MIGRATING_TO_V2.md").is_file():
        problems.append("docs/MIGRATING_TO_V2.md is missing")
    return problems


def run_checks(tag=None):
    """
    runs every release check
    :param tag: optional release tag to check against the version
    :returns: list of (check name, problems) pairs
    """
    files = tracked_files()
    return [
        ("version", check_version(tag)),
        ("changelog and migration guide", check_release_notes()),
        ("documentation links", check_links(files)),
        ("documented commands", check_commands(files)),
        ("tracked files", check_tracked_files(files)),
    ]


def main(argv=None):
    """
    command line entry point
    :param argv: optional argument list
    :returns: exit code
    """
    parser = argparse.ArgumentParser(prog="python -m scripts.release_check")
    parser.add_argument("--tag", help="release tag that must match the version")
    args = parser.parse_args(argv)
    failed = 0
    for name, problems in run_checks(args.tag):
        print(f"  {'FAIL' if problems else 'ok  '} {name}")
        for problem in problems:
            print(f"         {problem}")
        failed += bool(problems)
    if failed:
        print(f"release check: {failed} check(s) failed")
        return 1
    print(f"release check: ordixa {__version__} passed every check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
