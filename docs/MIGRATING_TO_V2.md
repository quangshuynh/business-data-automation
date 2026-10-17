# Migrating to Ordixa 2.0.0

2.0.0 is the first release of Ordixa as a product. The major version marks
the larger product surface, not a rewrite: v1.0.0 users keep the original
pipeline, and anyone who ran the Ordixa engine from `main` before this
release keeps their profiles, manifests, and results. The full list of
changes is in the [changelog](../CHANGELOG.md).

## Two products in one repository

| | Business Data Automation pipeline | Ordixa workflow engine |
| --- | --- | --- |
| Released in | v1.0.0 (August 2026) | 2.0.0 (first release) |
| Entry point | `python main.py` | `python -m app.ordixa COMMAND` |
| Inputs | fixed `data/customers.csv`, `orders.csv`, `payments.csv` | any CSV/XLSX export described by a TOML profile |
| Workflows | one reconciliation report | reconciliation, spreadsheet cleaning, dataset comparison |
| Outputs | `output/` CSV reports, optional PostgreSQL, FastAPI, dashboard | atomic, checksummed run directories with workbooks and manifests |
| Documentation | [ARCHITECTURE.md](ARCHITECTURE.md) | [ORDIXA.md](ORDIXA.md), [SPREADSHEET_WORKFLOWS.md](SPREADSHEET_WORKFLOWS.md) |

The original pipeline is still included and still runs as before. Ordixa
reuses its validators and reconciliation engine but does not write to
PostgreSQL, and the API and dashboard still read only what the original
pipeline persisted.

## What changed since v1.0.0

Everything under `python -m app.ordixa` is new relative to v1.0.0. It was
built on `main` in five merged steps before being released here:

| Step | Pull request | Added |
| --- | --- | --- |
| Phase 1A | [#1](https://github.com/quangshuynh/ordixa/pull/1) | versioned TOML import profiles, CSV/XLSX adapters, strict normalization, exceptions workbook, run manifests, `run` and `check-profile` |
| Phase 1B | [#2](https://github.com/quangshuynh/ordixa/pull/2) | text identifiers, identifier-collision safeguards, `inspect`, atomic run directories, data-handling guide |
| Interval 3 | [#3](https://github.com/quangshuynh/ordixa/pull/3) | Ordixa visual identity, the guided Harbor Lane demo, real screenshots |
| Interval 4 | [#4](https://github.com/quangshuynh/ordixa/pull/4) | read-only pilot preflight (`check-profile --input`), `verify`, pilot kit |
| Interval 5 | [#5](https://github.com/quangshuynh/ordixa/pull/5) | spreadsheet `clean` and `compare` with table profiles, the inventory demo |

The release itself added:

- **Profile preview.** `check-profile` now preflights clean and compare
  profiles as thoroughly as reconciliation ones, can preview a comparison
  with `--before`/`--after`, and explains any profile's column mapping and
  normalization with `--explain`. See
  [Previewing a profile](SPREADSHEET_WORKFLOWS.md#previewing-a-profile).
- **Comparison result.** Every comparison is assessed as complete, complete
  with warnings, or incomplete, so a column missing from one export or an
  unclassified record is never silently counted as unchanged. See
  [Comparison result](SPREADSHEET_WORKFLOWS.md#comparison-result).
- **CLI guidance.** `--help` examples and exit codes, a closing summary with
  the exact `verify` command, and hints after input errors.
- **Release checks.** `python -m scripts.release_check` and a validation-only
  release workflow; see [RELEASING.md](RELEASING.md).

## New CLI behavior

Command names, options that existed before, and exit code meanings are
unchanged. Differences an operator or script may notice:

| Change | Effect |
| --- | --- |
| `check-profile --input FILE` for a clean/compare profile is now a full preflight | text output is a preflight report instead of a list of counts; the `--json` report keeps every key it had and adds `readiness`, `findings`, `inputs`, and more |
| A header that suggests card, bank, government ID, or credential data | now blocks a clean/compare preflight (exit 3), as it already did for reconciliation; `clean` and `compare` themselves still only warn |
| `check-profile --json` without `--input` | still a usage error unless `--explain` (or `--before`/`--after`) is given |
| New options | `check-profile --explain`, `--before`, `--after` |
| `run`, `clean`, `compare` | print two more lines at the end: the run directory and its `verify` command; `compare` also prints the comparison result |
| `run --input` with a directory that does not exist | one input error (exit 3), without the repository-location warning |
| Personal-data header note | no longer fires on names of things such as `Product Name` or `Supplier Name` |

Scripts that only check exit codes, or parse `--json` output, need no change.

## Versioning

The application version is `2.0.0`, defined once in
`app/ordixa/__init__.py` and printed by `python -m app.ordixa --version`.
Runs record it in `manifest.json` under `result.code_version.ordixa`, next to
the git commit. Before this release the engine reported `0.1.0`; runs
written then keep that value.

Profile `version` fields are your own and are unaffected.

## Profile compatibility

Every reconciliation, clean, and compare profile that was valid before 2.0.0
is valid in 2.0.0 and produces the same results. There is no new profile
key and no `schema_version` change. Tests in `tests/test_ordixa_compatibility.py`
rerun the example profiles against stored pre-release runs and require
byte-identical deterministic outputs and identical fingerprints.

## Manifest compatibility

`manifest_version` is still `1`, and `verify` checks runs written before
2.0.0 unchanged (stored examples are in `tests/fixtures/runs-0.1.0`).

- Reconciliation and clean manifests have exactly the same fields.
- Compare manifests gain one field, `result.assessment`. It is outside the
  `result_fingerprint`, so a comparison of the same files keeps the
  fingerprint it had before 2.0.0.
- Deterministic CSV artifacts are byte-identical for the same inputs,
  profile, and code; the comparison workbook's Summary sheet gains a
  Comparison result section.

## Original pipeline compatibility

`python main.py`, the API, and the dashboard behave as in v1.0.0, with two
fixes made on `main` after v1.0.0 that change results only in edge cases:

- `build_report` in `app/reconciliation/reconcile.py` refuses customers,
  orders, or payments with duplicate identifiers instead of counting them
  twice. `main.py` already rejected such files during validation, so its
  outputs are unchanged.
- `customer_found` is now true for every order whose customer exists, even
  when that customer's optional name is blank (v1.0.0 reported false).

`openpyxl` is now a runtime dependency; reinstall with
`python -m pip install -r requirements.txt`.

## Known limitations

- Ordixa runs from a source checkout (`python -m app.ordixa`); it is not
  published to PyPI and has no installer, container image, or executable.
- It has been exercised only on fictional data; there are no validated
  customer deployments yet. Real customer files need the owner decisions in
  [pilot/DATA_DECISIONS.md](pilot/DATA_DECISIONS.md) first.
- Reconciliation still needs a shared order reference and covers only the
  files in one run; there is no cross-run history.
- Clean and compare handle one table per run, match only by an exact
  business key, and never resolve conflicting rows.
- The full lists are in [ORDIXA.md](ORDIXA.md#known-limitations) and
  [SPREADSHEET_WORKFLOWS.md](SPREADSHEET_WORKFLOWS.md#known-limitations).
