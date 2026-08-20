# Portfolio and Interview Guide

## One-line description

An end-to-end Python reconciliation system that validates related CSV datasets, quarantines rejected records, reconciles payments and refunds, optionally upserts clean data into PostgreSQL, and serves results through FastAPI and a responsive dashboard.

## Portfolio description

Business Data Automation models a back-office workflow where customer, order, and financial-transaction files arrive with inconsistent contact data, broken relationships, malformed values, and unreliable source status labels. The batch pipeline separates fatal dataset failures from row-level errors, emits explainable quarantine files, calculates order balances from exact-cent transaction amounts, and produces discrepancy-aware reconciliation output.

Validated records can be written transactionally through SQLAlchemy to PostgreSQL. FastAPI exposes read-only data and reconciliation endpoints, and a same-origin HTML/CSS/JavaScript dashboard turns those results into an operational view. The CLI remains usable without a database, keeping the original automation workflow independent from the optional persistence and API layers.

## Resume bullets

- Built a Python and Pandas pipeline that ingests three related CSV datasets, separates fatal schema errors from row-level failures, validates parent-child relationships, and produces audit-friendly quarantine and reconciliation outputs
- Implemented exact-cent reconciliation for payments, refunds, and signed adjustments, deriving unpaid, partial, paid, and overpaid states independently of source status labels
- Designed optional SQLAlchemy and PostgreSQL persistence with foreign-key and check constraints, transactional primary-key upserts, and graceful CSV fallback when database operations fail
- Exposed persisted records through read-only FastAPI endpoints and a responsive vanilla-JavaScript dashboard with status summaries, discrepancy alerts, search, and filtering
- Developed automated coverage across validation, reconciliation, persistence, API behavior, and the complete CSV-to-output workflow, with Ruff formatting and linting enforced by GitHub Actions

## Architecture explanation

The application has two entry paths that reuse the same business rules:

1. The batch path loads CSV files, validates structure, quarantines rejected rows, optionally persists clean rows, reconciles orders, and writes output files
2. The API path reads persisted records, adapts them through a small service, and calls the same reconciliation module before returning typed responses

The separation keeps responsibilities explicit:

- `main.py` orchestrates the batch workflow
- `app/validators` owns data-quality and quarantine decisions
- `app/reconciliation` owns financial calculations
- `app/db` owns ORM models, sessions, constraints, and persistence
- `app/services` coordinates database records with reconciliation logic
- `app/api` owns HTTP contracts and request-scoped dependencies
- `app/dashboard` provides a same-origin presentation layer

## Business scenario

A small operations team receives exports from customer, order, and payment systems. Some rows contain malformed contacts, invalid totals, duplicate IDs, broken references, refunds, or source labels that disagree with actual amounts. Manually reviewing every row is slow and makes it easy to discard valid business data along with bad records.

This project automates that control process:

- Unusable dataset structures stop immediately
- Isolated record failures are routed to explainable quarantine files
- Clean relationships continue through reconciliation
- Amounts, refunds, and adjustments determine financial truth
- Discrepancies are surfaced for human review
- Valid data can power API and dashboard reporting

## Interview talking points

### Why separate fatal errors from quarantine errors?

A missing required column means the dataset cannot be interpreted safely, so processing stops. A malformed email affects one customer, so that row is quarantined while unrelated valid records continue. This balances data safety with throughput.

### Why not trust the source payment status?

Status labels can be stale or inconsistent. The order total and signed transaction effects are the auditable financial inputs, so the calculated status is derived from those amounts. Source status remains metadata and can generate a discrepancy flag.

### How are refunds represented?

Source amounts remain readable: payments and refunds use positive amounts, while `transaction_type` determines whether the reconciliation effect is positive or negative. Adjustments are explicitly signed. This avoids ambiguous negative refund records.

### Why one reconciliation function?

Both CSV reports and API responses call the same report builder. Keeping one source of financial truth prevents subtle drift between batch and web results.

### Why use primary-key upserts?

They make repeat imports safe from duplicate-key failures and allow corrected source rows to update existing records. This is incremental upsert behavior, not full snapshot synchronization; records missing from a later file are not automatically deleted.

### Why no repository or dependency-injection framework?

The application has one SQLAlchemy implementation and a small number of clear responsibilities. Additional interfaces would add ceremony without improving substitution or testing. Those patterns would become reasonable if multiple data sources or more complex domain services emerged.

### What would you improve for production scale?

- Add Alembic migrations
- Add authenticated and authorized access before exposing customer contact data
- Add live PostgreSQL and Docker integration tests in CI
- Replace row-wise merges with bulk upserts for larger imports
- Move large reconciliation queries toward SQL aggregation and pagination
- Add transaction dates, observability, and reconciliation-run history
- Define snapshot synchronization or batch-version semantics for stale records

## Demo walkthrough

1. Show the three source CSV files and explain their relationships
2. Run `python main.py`
3. Open the reconciliation report and one quarantine file
4. Point out the payment plus refund on order `5001`
5. Start PostgreSQL and load validated records
6. Start FastAPI and open `/docs`
7. Open `/dashboard/`, filter by partial status, and show the discrepancy message
8. Run `python -m pytest -q`
9. Close with the architecture diagram and one deliberate limitation

## Screenshot checklist

Capture real application screens after loading the sample data:

- Dashboard overview showing summary cards and the reconciliation table
- Dashboard filtered to partial or flagged orders
- FastAPI OpenAPI page with the four data/reporting endpoints and two health checks
- Terminal showing a successful batch run
- Terminal showing the passing test suite

Do not use generated mock screenshots in the portfolio. Real captures make the demo credible and keep presentation aligned with the repository state.
