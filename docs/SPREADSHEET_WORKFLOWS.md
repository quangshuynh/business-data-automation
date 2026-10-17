# Ordixa: spreadsheet cleaning and comparison

Two deterministic workflows for single-table exports such as an inventory
list or a price list:

- **`clean`** turns one inconsistent CSV/XLSX export into a validated,
  standardized CSV plus an issue report.
- **`compare`** cleans two versions of the same export with the same rules,
  matches records by an explicit business key, and writes a change report
  workbook.

Both are product hypotheses built on the existing import foundation, not
evidence of customer demand. They have been exercised only on fictional data.

## Reconciliation versus cleaning and comparison

| | `run` (reconciliation) | `clean` / `compare` |
| --- | --- | --- |
| Input | a directory of order, payment, and customer exports | one file, or a before and an after file |
| Profile | reconciliation profile (`[datasets.*]`) | table profile (`[workflow]`, `[columns.*]`) |
| Model | canonical orders, payments, customers | the columns the profile declares, nothing more |
| Result | ledger, exceptions workbook, money totals | cleaned CSV, or added/removed/modified records |
| Shared | readers, size limit, exact parsers, formula guard, output-path rules, atomic run directories, manifests, `verify` | |

Inventory, price lists, and similar tables are never forced into the order
and payment model. The two profile kinds reject each other, and each error
names the right command.

## Quick start

```bash
python -m app.ordixa.inventory_demo            # clean, compare, and verify the fictional store

python -m app.ordixa clean --profile examples/ordixa/profiles/inventory-clean.toml \
  --input examples/ordixa/exports/inventory/inventory-before.csv --out output/inventory-clean
python -m app.ordixa compare --profile examples/ordixa/profiles/inventory-compare.toml \
  --before examples/ordixa/exports/inventory/inventory-before.csv \
  --after examples/ordixa/exports/inventory/inventory-after.csv --out output/inventory-comparison
python -m app.ordixa verify --run output/inventory-comparison/run-<id> \
  --input examples/ordixa/exports/inventory
```

`check-profile` validates a table profile, and with `--input <file>` dry-runs
the cleaning in memory and prints counts and issue codes without writing
anything (add `--json` for a machine-readable report).

## Table profiles

```toml
schema_version = 1

[workflow]
kind = "compare"                  # or "clean"

[profile]
name = "inventory-compare"
version = "1.0.0"

[input]
formats = ["csv", "xlsx"]
csv_encoding = "utf-8-sig"
# sheet = "Inventory"             # XLSX worksheet; defaults to the first

[amounts]                         # required when a decimal column is declared
currency = "USD"
currency_symbols = ["$"]
thousands_separator = ","
decimal_separator = "."
max_decimal_places = 2
negative_styles = ["minus"]

[table]
key = ["sku"]                     # business key; several columns form a compound key
blank_values = ["N/A", "-"]       # exact tokens, after trimming, treated as blank
date_formats = ["%Y-%m-%d", "%m/%d/%Y"]

[columns.sku]                     # output name; tables are output in this order
source = "Item SKU"               # header in the export (explicit rename)
type = "identifier"
required = true

[columns.product_name]
source = "Product Name"
required = true
whitespace = "collapse"

[compare]                         # compare profiles only
ignore = ["last_counted"]         # cleaned but not compared
```

| Column type | Accepts | Output |
| --- | --- | --- |
| `text` (default) | any text | trimmed text, case and spelling kept |
| `identifier` | letters, digits, `- _ . / : #`, no spaces | exact text: `000123`, `SKU-0042`, `ABC-009` |
| `decimal` | the `[amounts]` format; XLSX numbers | exact `Decimal`, two places (`12.5` becomes `12.50`) |
| `integer` | digits with an optional leading minus | whole number (`007` becomes `7`) |
| `date` | the declared `date_formats`; XLSX dates | `YYYY-MM-DD` |

Rules worth knowing:

- Only declared columns are written. Unmapped source columns are left out of
  every output and named (headers only) in a note.
- Every cell is trimmed. `whitespace = "collapse"` (text columns only) also
  turns runs of inner spaces into one. Nothing is lowercased, title-cased, or
  otherwise rewritten.
- Business keys must be `identifier` or `text` columns, so `007` and `7`, or
  `000123` and `123`, are always different records. Key columns are always
  required. Compare profiles must declare a key; clean profiles may omit it.
- Amounts are never rounded: more decimal places than allowed, the wrong
  separators, or an unconfigured negative style reject the row. The decimal
  limit is two places, as for reconciliation.
- A date matching two declared formats with different results (`03/04/2026`
  with both `%m/%d/%Y` and `%d/%m/%Y`) is rejected as ambiguous.
- A required column missing from the header stops the run (exit 3) and lists
  every missing column. A missing optional column is blank and noted.

## Cleaning

Each row is mapped, trimmed, blank-normalized, and typed. Then:

| Situation | Outcome |
| --- | --- |
| Invalid value, or blank required value | **Rejected**, with column, issue code, and source row |
| Row identical to an earlier row after normalization | **Removed duplicate**; the first copy is kept |
| Several different rows share a business key | **Rejected**, every copy (`conflicting_key`); none is chosen |
| A valid row shares its key with a rejected row | **Rejected** (`key_on_rejected_row`) until the source is fixed |
| Row with a different number of cells than the header | **Rejected** (`malformed_row`) |

Duplicate keys therefore come in three kinds that are reported separately:
exact duplicate rows (harmless, collapsed), duplicate identifiers (counted in
`duplicate_keys`), and conflicting records (held back, never merged).

The cleaned CSV keeps source order and the profile's column order. Issue
messages name columns and rows but never quote cell values; the offending
value, where one exists, is in a separate `value` column so it can be fixed
at the source.

## Comparison

Both files are cleaned with the same profile, then indexed by business key.
Row position and column order play no part. Every key ends in exactly one
category:

| Category | Meaning |
| --- | --- |
| Added | key only in the later export |
| Removed | key only in the earlier export |
| Modified | key in both; at least one compared column differs |
| Unchanged | key in both; every compared column is equal |
| Ambiguous | conflicting rows share the key in either export |
| Invalid | a row with the key was rejected in either export |

Ambiguous and invalid keys are never counted as added, removed, or modified:
a product whose later row has a blank price is invalid, not removed. Rows
whose key itself could not be read are counted separately.

Values are compared after the profile's normalization, so `$1,000`, `1000`,
and `1000.00` are equal, as are `10/05/2026` and `2026-10-05`, a padded cell
and a trimmed one, and a configured blank token and an empty cell. Anything
the profile does not normalize is a change: capitalization, punctuation,
inner spacing (unless `collapse`), accents, and Unicode spelling. A column
missing from either file is not compared and is noted, rather than turning
every record into a change.

## Outputs

Each run publishes a new `run-<timestamp>-<id>` directory through the same
staging-then-rename path as reconciliation runs; failures publish nothing and
earlier runs are never overwritten.

| Workflow | Files |
| --- | --- |
| clean | `cleaned_data.csv`, `cleaning_issues.csv`, `manifest.json` |
| compare | `comparison_report.xlsx`, `added_records.csv`, `removed_records.csv`, `modified_values.csv`, `comparison_issues.csv`, `manifest.json` |

The change report workbook has five sheets in the Ordixa palette:
**Summary** (record counts, changed values by column, reading guide,
processing details, input checksums), **Added Records**, **Removed Records**,
**Modified Records** (business key, changed column, previous value, new
value, and the signed change for numbers), and **Data Quality Issues**. Every
value passes the existing formula-injection guard, identifiers are text
cells, and nothing is a formula.

**Manifests** follow the reconciliation layout with explicit
`"workflow": "clean"` or `"compare"` and `"workflow_version": 1`
(reconciliation manifests have no workflow field and are unchanged). The
`result` section records the profile name, version, kind, key, and SHA-256,
the code version, each input's role, name, SHA-256, and row count, row and
issue counts, comparison totals, artifact row counts, and a
`result_fingerprint` over the logical result (records, changes, issues,
counts), not timestamps or directory names. Manifests hold no cell values.

**Verification** uses the existing command. For a comparison whose files sit
in two folders, repeat `--input`:

```bash
python -m app.ordixa verify --run output/inventory-comparison/run-<id> \
  --input customer-data/store/week-41 --input customer-data/store/week-42
```

## Exit codes

The same as `run`: 0 success, 2 profile problem (including the wrong profile
kind), 3 input problem, 4 integrity cross-check failure, 5 output location or
disk problem, 1 unexpected error with details withheld unless `ORDIXA_DEBUG=1`.

## Size and performance

Files are read fully into memory under the existing 200 MB per-file limit.
Comparison uses one dictionary lookup per key, so time grows linearly with
row count. Measured on a laptop with the inventory profile (seven columns),
end to end including the workbook: a 10,000-row comparison takes about 2
seconds and a 100,000-row comparison about 12 seconds, with a Python heap
peak of roughly 370 MB for the two 100,000-row files. Very wide tables or
files near the size limit need proportionally more memory; split them by
location or category if a run is too slow.

## Privacy

- Cleaning and comparison run locally and send nothing anywhere.
- The terminal shows file names, counts, and issue codes, never cell values.
- Headers that suggest card, bank, government ID, or credential data are
  flagged by name, and mapped headers that suggest personal data are noted.
  This is the preflight's header heuristic, not a privacy scanner.
- **The change report and CSVs contain previous and current values.** Treat a
  comparison run as customer-sensitive output, under the same rules as
  reconciliation runs in [DATA_HANDLING.md](DATA_HANDLING.md).

## Known limitations

- One table per run; no joins, lookups, or cross-file rules.
- No fuzzy matching, no record identity from row position, and no automatic
  resolution of conflicting rows. Ambiguous keys must be fixed at the source.
- Profiles are written by hand; there is no column-mapping UI and no
  inferred profile. `inspect` can help describe an unfamiliar file.
- Decimal columns allow at most two decimal places and one set of separators
  per profile; integers accept no thousands separators.
- Blank tokens are exact, case-sensitive matches.
- Unicode is compared exactly; visually identical but differently encoded
  text counts as a change.
- XLSX identifiers stored as numbers have already lost leading zeros in the
  workbook; they cannot be restored. Formula cells are read by cached value.
- No history: each comparison covers exactly two files.

## Design decisions

- **A separate table profile kind** rather than new reconciliation dataset
  roles: inventory rows are not orders or payments, and a second schema with
  the same TOML conventions keeps every existing profile valid unchanged.
- **Reuse, not a framework.** The workflows reuse the CSV/XLSX readers, size
  limit, identifier, amount, and date parsers, formula guard, workbook
  styles, output-path checks, run publication, and verification. The new
  code is `tabular_profile.py` (profiles), `tabular.py` (cleaning and
  comparison), `tabular_outputs.py` and `change_report.py` (run directories
  and workbook), and `inventory_demo.py`.
- **Hold back instead of choose.** Wherever two rows disagree about one key,
  every copy is withheld and reported; the operator fixes the source.
- **Canonical text for comparison.** Values are compared by their cleaned
  canonical form, so only the profile's declared rules decide what counts as
  a formatting difference.
