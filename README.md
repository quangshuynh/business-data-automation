<p align="center">
  <img src="docs/images/ordixa-logo.png" alt="Ordixa icon" width="256">
</p>

# Ordixa
<p align="center">
  <a href="https://github.com/quangshuynh/ordixa/actions/workflows/ci.yml">
    <img src="https://github.com/quangshuynh/ordixa/actions/workflows/ci.yml/badge.svg" alt="CI">
  </a>
  <a href="https://github.com/quangshuynh/ordixa/releases">
    <img src="https://img.shields.io/github/v/release/quangshuynh/ordixa" alt="Release">
  </a>
  <img src="https://img.shields.io/badge/python-3.14-blue" alt="Python 3.14">
</p>

**Less busywork. More clarity.**

Turn messy business exports into clear, actionable reports. Ordixa imports
CSV and Excel files, applies repeatable validation rules, reconciles orders
and payments, and puts every exception in a structured workbook.

<p align="center">
  <img src="docs/images/workbook-exceptions.png" width="900"
       alt="Exceptions sheet of an Ordixa workbook listing unpaid, partially paid, and overpaid orders with a note on what to check">
</p>
<p align="center"><em>Exceptions sheet from the fictional demo, rendered from the generated workbook.</em></p>

## What Ordixa does

A small business already has the exports: orders from a storefront, payments
from a processor, sometimes a customer list. Ordixa turns one batch of those
files into a reviewed result:

1. **Reads CSV and XLSX exports** read-only, and can describe an unfamiliar
   file before any setup (`inspect`).
2. **Applies a versioned import profile**: a short TOML file that maps the
   customer's headers, ID prefixes, date formats, status labels, and refund
   signs onto one canonical model. Profiles are validated before any data is read.
3. **Validates and normalizes** every row with exact decimal arithmetic.
   Problems are rejected, kept with a warning, or excluded by rule, and each
   one is traced to its source file and row.
4. **Reconciles** payments, refunds, and adjustments against order totals
   using the shared order reference, and classifies each order as paid,
   partially paid, unpaid, or overpaid.
5. **Writes an Excel exceptions workbook** (Summary, Exceptions, Rejected Rows,
   Full Ledger) plus CSV artifacts.
6. **Records an auditable manifest** with input and output checksums, counts,
   totals, and a result fingerprint, so a run can be verified later.

Everything runs locally. No database, account, or network access is needed.

## Product preview

<table>
  <tr>
    <td width="50%"><img src="docs/images/workbook-summary.png" alt="Summary sheet with financial totals, exception counts, a reading guide, data quality counts, and input checksums"></td>
    <td width="50%"><img src="docs/images/cli-demo-run.png" alt="Terminal output of the seven-step demo ending with nine passing verification checks"></td>
  </tr>
  <tr>
    <td><em>Summary sheet: totals, exceptions, data quality, input fingerprints.</em></td>
    <td><em>The guided demo, from source exports to verified manifest.</em></td>
  </tr>
</table>

The [demo walkthrough](docs/DEMO.md) has the full gallery: read-only
inspection, Rejected Rows, and Full Ledger.

## Quick start

Prerequisites: Python 3.14 (the version CI uses) and Git.

```bash
git clone https://github.com/quangshuynh/ordixa.git
cd ordixa
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Run the complete fictional demo (inspect, validate the profile, reconcile,
write the workbook, verify the manifest):

```bash
python -m app.ordixa.demo
```

Or run each step yourself:

```bash
python -m app.ordixa check-profile --profile examples/ordixa/profiles/harbor-lane.toml
python -m app.ordixa inspect --input examples/ordixa/exports/demo
python -m app.ordixa run --profile examples/ordixa/profiles/harbor-lane.toml \
  --input examples/ordixa/exports/demo --out output/demo
```

Each run creates `output/demo/run-<timestamp>-<id>/` containing
`ordixa_exceptions.xlsx`, `reconciliation_ledger.csv`, `rejected_rows.csv`,
and `manifest.json`. Open the `.xlsx` file in Excel or LibreOffice. `output/`
is git-ignored.

## Features

| Capability | Status |
| --- | --- |
| CSV and XLSX input; several files per dataset (for example two months) | Implemented |
| Versioned TOML import profiles with strict validation and spelling hints | Implemented |
| Read-only `inspect` for unfamiliar exports (prints no cell values) | Implemented |
| Numeric or exact-text identifiers (`#1001`, `ORD-2026-00142`, `00012345`) | Implemented |
| Exact `Decimal` money parsing: separators, symbols, negative styles | Implemented |
| Duplicate, conflicting-duplicate, and identifier-collision safeguards | Implemented |
| Paid / partial / unpaid / overpaid reconciliation with refunds and adjustments | Implemented |
| Branded four-sheet Excel workbook, formula-injection protected, print-ready | Implemented |
| Run manifest with SHA-256 checksums, result fingerprint, and verification | Implemented |
| Atomic run directories; earlier runs are never overwritten | Implemented |
| Original CSV pipeline with optional PostgreSQL, FastAPI, and dashboard | Implemented (legacy path) |
| Matching payments to orders from earlier runs | Planned |
| Vendor connectors (Shopify, Square, Stripe, QuickBooks) | Not implemented |
| Hosted self-service app, accounts, scheduling | Not implemented |

## Architecture

```text
source exports (CSV/XLSX)
  → import profile        header, ID, date, status, and sign mapping
  → normalization         exact decimals and dates, text or numeric identifiers
  → validation            rejected / kept with warning / excluded, with source row
  → reconciliation        shared order reference; totals cross-checked
  → workbook + manifest   run-<id>/ written atomically, checksummed
```

The reconciliation engine is shared with the original Business Data
Automation pipeline (`main.py`), which still runs unchanged.
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) covers the module layout, the
legacy pipeline, the API, the dashboard, and the test strategy.

## Documentation

| Document | Contents |
| --- | --- |
| [docs/ORDIXA.md](docs/ORDIXA.md) | CLI, profile reference, identifiers, normalization, validation, workbook, manifests, limitations |
| [docs/DEMO.md](docs/DEMO.md) | The fictional Harbor Lane walkthrough, expected results, screenshot gallery |
| [docs/DATA_HANDLING.md](docs/DATA_HANDLING.md) | Procedures for receiving, processing, and deleting real customer files |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Module layout, legacy pipeline, PostgreSQL, FastAPI, dashboard, Docker, testing |
| [docs/BRAND.md](docs/BRAND.md) | Ordixa colors, typography, and layout rules |
| [examples/ordixa](examples/ordixa/README.md) | Fictional exports, profiles, and hand-computed expectations |
| [docs/PORTFOLIO.md](docs/PORTFOLIO.md) | Portfolio narrative for the original pipeline |

## Limitations

Ordixa is an early, tested foundation, exercised only on fictional data.

- **Shared order references are required.** Payments are matched to orders by
  the order reference alone: no date, amount, or fuzzy matching.
- **A run reconciles only the files it is given.** A payment for an order from
  an earlier export is reported as `order_not_in_run`; nothing persists
  between runs.
- **CSV and XLSX only**, one currency per profile, files up to 200 MB.
  Legacy `.xls` and non-comma delimited files are not supported.
- **No vendor integrations.** The demo exports imitate common storefront and
  processor layouts but are not official Shopify, Square, Stripe, or
  QuickBooks exports; each real format needs a profile checked against samples.
- **No customer-facing self-service app.** Ordixa is a command-line tool that
  an operator runs; the workbook is the deliverable.
- Zero-total orders are rejected, and the workbook is not an accounting ledger.

The full list is in [docs/ORDIXA.md](docs/ORDIXA.md#known-limitations).

## Development

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
ruff check .
ruff format --check .
```

CI runs the same checks, then smoke-tests the CLI and the demo, on every push
and pull request. Screenshots are regenerated from a real demo run with
`python -m scripts.capture_screenshots` (needs LibreOffice and PyMuPDF; see
the script header).

## License

[MIT](LICENSE) © 2026 Quang. Ordixa grew out of the
Business Data Automation project in this repository.
