# Releasing Ordixa

A maintainer checklist. Releases are tagged and published by hand after the
checks below pass; no workflow can publish a release.

## Version

The version is defined once, as `__version__` in `app/ordixa/__init__.py`.
Bump it on the release branch together with a dated `## [X.Y.Z] - YYYY-MM-DD`
section and link definition in [CHANGELOG.md](../CHANGELOG.md).

## Checks

On the release branch, from a clean checkout:

```bash
python -m pip install -r requirements-dev.txt
python -m pip check
ruff format --check .
ruff check .
python -m pytest -q
python -m scripts.release_check --tag vX.Y.Z
python -m app.ordixa.demo --out output/release-demo
python -m app.ordixa.inventory_demo --out output/release-inventory
```

`scripts/release_check.py` checks that `--version` and the tag match
`__version__`, that the changelog has the release section, that every
relative link and heading anchor in tracked Markdown resolves, that every
documented `python -m app.ordixa` command parses, and that tracked files
contain no `.env`, `customer-data/`, run outputs, stray spreadsheets,
common secret formats, or email addresses outside reserved example domains.

## Automation

- [CI](../.github/workflows/ci.yml) runs formatting, lint, tests, the
  release checks, and the CLI and demo smoke tests on every branch push and
  pull request.
- [Release validation](../.github/workflows/release.yml) runs on pull
  requests from `release/*` branches, on `v*` tags, and on demand. It reruns
  CI and adds a clean runtime-only installation in a new virtual environment,
  the release checks against the tag, both demos and `verify` from that
  installation, and `pip-audit` over the pinned requirements. Its
  permissions are read-only; it uses no secrets and publishes nothing.

## Publishing

1. Open a pull request from `release/ordixa-vX.Y.Z` into `main`; wait for CI
   and release validation to pass and review the diff.
2. Merge it, then confirm the merge commit is on `origin/main` and CI on
   `main` passed.
3. Confirm the tag does not exist yet, then tag that commit:
   `git tag -a vX.Y.Z <commit> -m "Ordixa vX.Y.Z"` and push the tag.
4. Wait for release validation on the tag to pass.
5. Publish the GitHub release from the tag with notes taken from the
   changelog section. GitHub attaches the source archives; do not describe
   them as installable packages.

Never tag a feature branch, force-push, or rewrite a published tag. If a
gate fails after tagging, fix it on a new branch and release a new patch
version.
