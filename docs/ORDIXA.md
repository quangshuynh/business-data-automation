# Ordixa: profile-driven imports and exceptions workbook

Ordixa is the direction this project is evolving toward: a reusable tool that
takes the order and payment exports a small business already has, maps them
through a declared import profile, and produces a reviewable reconciliation
workbook. Phase 1A adds that import path alongside the original Business Data
Automation pipeline, reusing its validation helpers and reconciliation engine.

Status: an early, tested foundation. It has been exercised only against the
fictional exports in [`examples/ordixa`](../examples/ordixa). It is not
production-ready, has no commercial validation, and does not claim to read
arbitrary Shopify, Square, Stripe, QuickBooks, or other vendor exports. Each
real export format needs a profile written and checked against sample files.

```text
customer export (CSV/XLSX)
    → profile mapping and strict normalization
    → canonical validated rows (errors / warnings / exclusions)
    → existing reconciliation engine (app/reconciliation)
    → independent totals cross-check
    → run directory: workbook, CSV artifacts, manifest
```

## Quick start

```powershell
python -m pip install -r requirements.txt
python -m app.ordixa run `
  --profile examples/ordixa/profiles/harbor-lane.toml `
  --input examples/ordixa/exports/problematic `
  --out output/ordixa
```

PostgreSQL is not required. Validate a profile without processing data:

```powershell
python -m app.ordixa check-profile --profile examples/ordixa/profiles/harbor-lane.toml
```

| Exit code | Meaning |
| --- | --- |
| 0 | Run completed (rejected rows are reported, not fatal) |
| 1 | Unexpected internal error |
| 2 | Invalid profile or command usage |
| 3 | Input problem: missing directory, dataset, column, or unreadable file |
| 4 | Reconciliation integrity check failed; nothing written |
| 5 | Output location refused or not writable |

`--out` is a parent directory. Output inside the input directory or inside the
tracked `examples/`, `data/`, `tests/`, or `app/` directories is refused.
Input files are only read.

## Import profiles

Profiles are small TOML files (`schema_version = 1`). They are validated before
any data is read; every problem is reported at once with its key path, and
unknown keys are rejected with a spelling suggestion. The annotated example is
[`harbor-lane.toml`](../examples/ordixa/profiles/harbor-lane.toml).

| Section | Keys | Notes |
| --- | --- | --- |
| `[profile]` | `name`, `version`, `description` | name is lowercase-hyphenated; version is `MAJOR.MINOR.PATCH` |
| `[input]` | `formats`, `csv_encoding` | formats from `csv`, `xlsx`; encoding defaults to `utf-8-sig` |
| `[amounts]` | `currency`, `currency_symbols`, `thousands_separator`, `decimal_separator`, `max_decimal_places`, `negative_styles` | one ISO currency per profile; at most 2 decimal places; negatives as `minus` and/or `parentheses` |
| `[reconciliation]` | `missing_customer` | `warning` (default) or `error` |
| `[datasets.<role>]` | `required`, `files`, `sheet`, `optional_columns`, `date_formats`, `excluded_statuses`, `refund_amounts` | roles are `customers` (optional), `orders`, `payments` |
| `[datasets.<role>.columns]` | canonical field = source header | `name` may list several columns, joined with a space |
| `[datasets.<role>.id_prefixes]` | canonical id field = literal prefix | `#1001` → `1001`, `PMT-260801` → `260801` |
| `[datasets.payments.value_maps.status]` | source label = canonical status | targets: `paid`, `partial`, `pending`, `refunded` |
| `[datasets.payments.value_maps.transaction_type]` | source label = canonical type | targets: `payment`, `refund`, `adjustment` |

Canonical fields per role:

| Role | Required | Optional |
| --- | --- | --- |
| customers | `customer_id` | `name`, `email`, `phone` |
| orders | `order_id`, `date`, `total` | `customer_id`, `currency` |
| payments | `payment_id`, `order_id`, `amount`, `transaction_type`, `status` | `payment_date`, `currency` |

Deliberately unsupported: expressions, computed columns, conditional mappings,
multi-currency profiles, and fuzzy header matching. Value maps are matched
case- and whitespace-insensitively; a label that is not in the map is a
blocking error, never a guess. Without a value map only the canonical labels
themselves are accepted.

## Input requirements

- Files are found in the `--input` directory (not subdirectories) by each
  role's `files` patterns. Several files per role are concatenated, so two
  reporting periods can be processed in one run. A file matching two roles
  stops the run.
- The first row is the header. Mapped columns must exist exactly as named
  unless listed in `optional_columns`; a missing column stops the run and
  names the closest header found.
- CSV cells are read as text with no type inference. XLSX cells keep their
  native types: real date cells and numeric cells are used directly (they are
  not ambiguous), while text cells go through the same parsing as CSV. Only
  cached values of formula cells are read; formulas are never evaluated.
- Identifiers must be positive whole numbers after removing a declared prefix.

## Normalization rules

**Dates.** Only the declared `strptime` formats are tried; four-digit years are
required. If a value parses under two declared formats to different dates
(`03/04/2026` with both `%m/%d/%Y` and `%d/%m/%Y`) it is rejected as ambiguous
and both readings are shown. Impossible dates (`2026-02-30`) are reported as
such. A timestamp with an offset keeps the calendar date written in the
export; nothing is shifted to UTC or another zone.

**Money.** Amounts are parsed into `Decimal` from text; floats are never used
for financial arithmetic. Thousands grouping must be well formed (`1,234.56`
is valid, `12,34` and `1.234,56` are not under a US profile), more decimal
places than allowed is an error, and only declared currency symbols are
stripped. A currency column that does not match the profile currency rejects
the row; currencies are never converted. A blank currency is a warning.

**Signs.** Payments and refunds must be positive after normalization;
adjustments are signed and must be non-zero. `refund_amounts = "negative"`
means refunds arrive as negative numbers and are stored as positive refund
amounts; a refund with the wrong sign is rejected.

## Validation severity

| Severity | Effect | Examples |
| --- | --- | --- |
| Error (blocking) | row rejected, not reconciled | invalid or missing identifier, amount, or order date; unmapped status or type; currency mismatch; refund sign; non-positive total; payment for a rejected order or an order not in this run; conflicting duplicate identifiers |
| Warning | row kept and reconciled | malformed email, missing or non-10-digit phone, missing name, unknown or rejected customer reference (default), unreadable optional payment date, blank currency |
| Excluded | row omitted from totals on purpose | statuses listed in `excluded_statuses`, such as `Failed` or `Voided` |

**Behavior change versus the legacy pipeline.** In `main.py`, an invalid email
or phone quarantines the customer and, through it, every related order and
payment. In the Ordixa path those problems are warnings and the money is still
reconciled. `main.py` is unchanged because its PostgreSQL schema requires
non-null contact fields.

**Duplicates.** Rows sharing an identifier with identical content are counted
once (the first by file name and row is kept; later copies are listed as
rejected). Rows sharing an identifier with different content are all rejected.
The engine itself now refuses duplicate customer, order, or payment
identifiers, and every run cross-checks the ledger against independent sums of
accepted rows; a mismatch stops the run (exit code 4).

**Matching.** Payments are matched to orders only by the shared order
identifier. There is no date, amount, customer, or fuzzy matching.

## Workbook

`ordixa_exceptions.xlsx` has four sheets:

| Sheet | Contents |
| --- | --- |
| Summary | order value, payments, refunds, signed adjustments, net received, amount reconciled to orders, outstanding balances, overpayments, exception counts, per-dataset row outcomes, processing metadata, input file fingerprints |
| Exceptions | unpaid, partially paid, and overpaid orders plus paid orders with discrepancy flags, with amounts and transaction IDs |
| Rejected Rows | every issue: dataset, source file and row, record ID, outcome, whether it prevented processing, issue code, field, value, reason, original mapped values |
| Full Ledger | every reconciled order with payment, refund, and adjustment breakdown, net paid, balances, status, flags, transaction IDs, last payment date, and source location |

Money is written as numeric cells with a two-decimal format, dates as date
cells. Tables have frozen header rows and auto-filters. Text from exports is
stored as string cells; values that could start a formula (`=`, `+`, `-`, `@`,
tab, CR) are prefixed with an apostrophe unless they are plain numbers such as
`-$89.00`. The workbook contains no formulas, external links, or macros.

## Run outputs and manifests

Each run creates `run-<UTC timestamp>-<random>` under `--out`:

| File | Deterministic | Contents |
| --- | --- | --- |
| `ordixa_exceptions.xlsx` | no (run ID and timestamps) | workbook above |
| `reconciliation_ledger.csv` | yes | full ledger |
| `rejected_rows.csv` | yes | issues, without the original-values column |
| `manifest.json` | no | see below |

The manifest separates `result` (stable for identical inputs, profile, and
code: status, profile name/version/SHA-256, code version and git commit,
input file names with SHA-256 and row counts, row and issue counts, totals,
and a `result_fingerprint` hashing the ledger, issues, and summary) from
`execution` (run ID, start/finish/reconciliation timestamps, directory name).
`outputs` lists each artifact's SHA-256 and whether it is deterministic. The
manifest holds no names, emails, phone numbers, or row values; it does hold
input file names, so avoid putting personal data in file names.

**Reruns.** Re-running the same inputs creates a new directory; earlier runs
are never overwritten. Two runs of identical inputs with the same profile and
code produce an identical `result` section and byte-identical CSV artifacts.

## Fictional fixtures

[`examples/ordixa`](../examples/ordixa) contains a clean baseline and a
problematic set, each split into August and September 2026 periods, with the
expected results computed by hand. Tests compare implementation output with
those hand-entered values in `tests/ordixa_golden.py`.

## Known limitations

- **No cross-run history.** Each run reconciles only the files it is given. A
  payment for an order from an earlier export is rejected as
  `order_not_in_run`; include both periods' order files in the same run
  instead. Nothing is persisted between runs.
- **Shared identifiers required.** Exports without a common order reference
  cannot be reconciled in this phase.
- **Integer identifiers.** After prefix removal, identifiers must be digits.
  Alphanumeric vendor IDs (for example `pay_8KQ2`) are not supported yet.
- **One currency per run**, no conversion.
- **Profile import path does not write to PostgreSQL**, and the API and
  dashboard still read only from the legacy persisted data.
- The fixtures imitate vendor styles; real exports have more columns, more
  statuses, and edge cases these profiles have not seen.
- Source status mapping is per label; it cannot depend on transaction type.

## Data handling

Exports contain personal data. Ordixa runs locally, sends nothing over the
network, and does not modify inputs. The workbook and `rejected_rows.csv`
include customer names, emails, and offending values because reviewers need
them; store run directories with the same care as the exports. `output/` is
git-ignored. Do not commit real customer exports to this repository.

## Roadmap (not implemented)

1. Profile authoring help: a header inspection command and starter profiles
   validated against real, consented sample exports.
2. Opaque string identifiers and per-dataset currency.
3. Optional persisted import history so later payments can be matched to
   earlier orders explicitly and auditably.
4. Workbook review loop: carry reviewer notes between runs.
5. Packaging (`pip install` entry point) once the CLI stabilizes.

Hosted multi-tenant service, accounts, billing, scheduling, and integrations
are out of scope until the import foundation is proven with real data.
