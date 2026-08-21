# Business Data Automation

<p align="center">
  <a href="https://github.com/quangshuynh/business-data-automation/actions">
    <img src="https://github.com/quangshuynh/business-data-automation/actions/workflows/ci.yml/badge.svg" alt="CI">
  </a>
  <a href="https://github.com/quangshuynh/business-data-automation/releases">
    <img src="https://img.shields.io/github/v/release/quangshuynh/business-data-automation" alt="Release">
  </a>
  <img src="https://img.shields.io/badge/tests-52%20passing-brightgreen" alt="Tests: 52 passing">
  <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+">
</p>

A tested Python data pipeline that validates incoming customer, order, and
payment CSV files, quarantines invalid records, reconciles financial balances,
can persist validated data to PostgreSQL, and exposes results through FastAPI.

[Portfolio narrative, resume bullets, and interview guide](docs/PORTFOLIO.md)

<p align="center">
  <img src="./docs/images/dashboard.png"
       alt="Business Data Automation reconciliation dashboard"
       width="900">
</p>

<p align="center">
  <em>Reconciliation dashboard showing financial status, balances, and flagged discrepancies</em>
</p>

## What the system does

- Loads customer, order, and payment CSV datasets
- Treats missing columns and duplicate primary IDs as fatal structural failures
- Validates positive whole-number IDs and exact-cent financial amounts
- Normalizes customer contact information
- Quarantines invalid business records without stopping valid records
- Validates customer-to-order and order-to-payment relationships
- Reconciles payments, refunds, and signed adjustments against order totals
- Produces paid, partial, unpaid, and overpaid financial statuses
- Writes reconciliation and quarantine CSV outputs
- Optionally persists validated records to PostgreSQL through SQLAlchemy
- Exposes persisted data and reconciliation results through a read-only FastAPI API
- Serves a responsive reconciliation dashboard from the FastAPI application
- Runs locally or with Docker Compose

## Architecture

```mermaid
flowchart LR
    CSV[Customer, order, and payment CSVs] --> CLI[Batch pipeline]
    CLI --> Validation[Validation and normalization]
    Validation -->|invalid records| Quarantine[Quarantine CSVs]
    Validation -->|valid records| Reconciliation[Reconciliation rules]
    Reconciliation --> Report[Reconciliation CSV]
    Validation -->|DATABASE_URL configured| Database[(PostgreSQL)]
    Database --> Service[Reconciliation service]
    Service --> Reconciliation
    Database --> API[FastAPI]
    Service --> API
    API --> Dashboard[Reconciliation dashboard]
```

Application responsibilities are separated by runtime role:

```text
app/
├── api/             HTTP routes, dependencies, and response schemas
├── db/              SQLAlchemy models, sessions, and persistence
├── reconciliation/  financial calculations and report construction
├── services/        database-to-business-logic coordination
├── validators/      structural and record-level validation
└── config.py        environment configuration

main.py              CSV batch entry point and pipeline orchestration
```

The API and batch workflow share the same reconciliation implementation. Database code stays outside `main.py`, while API routes delegate cross-layer reconciliation work to a focused service rather than duplicating calculations.

## Pipeline and validation strategy

```text
load CSV data
    ↓
validate dataset structure
    ↓
normalize and validate records
    ↓
quarantine invalid records
    ↓
persist valid records when configured
    ↓
build reconciliation report
    ↓
write report and quarantine outputs
```

Structural failures stop the run because the dataset cannot be interpreted safely:

- Missing required columns
- Duplicate customer, order, or payment IDs

Record-level failures are quarantined so valid business data can continue:

- Invalid email or phone
- Missing customer name
- Malformed order date
- Invalid order total
- Invalid transaction amount, type, or source status
- Missing or quarantined foreign-key parent

Invalid records remain in CSV quarantine files rather than PostgreSQL. Each rejected record is emitted in its normalized form with a `validation_errors` explanation, while validated records continue through the pipeline.

## Financial reconciliation

The calculated `financial_status` is derived from the order total and net transaction amount. It is never copied from the source payment `status`.

| Net paid amount | Financial status |
| --- | --- |
| Zero or less | `unpaid` |
| Greater than zero but less than the order total | `partial` |
| Equal to the order total | `paid` |
| Greater than the order total | `overpaid` |

Each payment record has a required `transaction_type`:

| Transaction type | Amount rule | Reconciliation effect |
| --- | --- | --- |
| `payment` | positive | increases net paid |
| `refund` | positive | decreases net paid |
| `adjustment` | non-zero and signed | applies its sign directly |

The report includes the net `amount_paid`, signed `balance_due`, non-negative `outstanding_balance`, `overpayment_amount`, `payment_count`, `financial_status`, discrepancy flags, and a UTC reconciliation timestamp.

Current discrepancy flags identify:

- Orders with no payments
- Overpaid orders
- Negative net transaction amounts
- Source payments marked paid when the net amount is unpaid or partial

## Example result

The included sample data contains a completed payment followed by a refund:

```text
order total:       129.99
payment:          +129.99
refund:            -10.00
net amount paid:   119.99
outstanding:        10.00
financial status: partial
```

Runtime-generated files are written under `output/`:

```text
output/reconciliation_report.csv
output/invalid_customers.csv
output/invalid_orders.csv
output/invalid_payments.csv
```

The runtime directory is ignored by Git because the reconciliation timestamp changes on every run. Stable examples from the included input data are committed under [`examples/output`](examples/output).

## Quick start: CSV workflow

Prerequisites:

- Python 3.14
- PowerShell commands below, or equivalent commands for your shell

Create an environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Run the CSV-only pipeline without configuring a database:

```powershell
python main.py
```

This validates the files under `data/` and writes results under `output/`.

## PostgreSQL setup

PostgreSQL is optional for the batch workflow and required for API data endpoints.

1. Create a PostgreSQL database and application user.
2. Copy the environment template:

   ```powershell
   Copy-Item .env.example .env
   ```

3. Replace the placeholder credentials in `.env`. The connection must use the Psycopg SQLAlchemy dialect:

   ```text
   DATABASE_URL=postgresql+psycopg://business_data_user:your_password@localhost:5432/business_data_automation
   ```

4. Run the pipeline:

   ```powershell
   python main.py
   ```

When configured, the pipeline creates missing tables and persists valid customers, orders, and transactions in one database transaction. Existing primary keys are merged, making repeated imports safe from duplicate-key failures. Database failures roll back and are logged without preventing CSV report generation.

Persistence uses incremental primary-key upserts. It does not treat each import as a complete snapshot, so records absent from a later input file are not automatically deleted.

To initialize empty tables without processing CSV files:

```powershell
python -c "from app.db.database import initialize_database; initialize_database()"
```

Secrets are read from `DATABASE_URL`; `.env` is ignored by Git and `.env.example` contains placeholders only.

### Existing database migration note

The payment transaction model requires `payments.transaction_type` and associated check constraints. SQLAlchemy `create_all()` creates the correct schema for new databases but does not alter an existing table. Existing databases must be migrated or recreated when their data is disposable.

For disposable Docker development data:

```powershell
docker compose down --volumes
docker compose up --build
```

## FastAPI

With `DATABASE_URL` configured, start the API:

```powershell
uvicorn app.api.api:api --reload
```

Interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/health` | application liveness check |
| GET | `/ready` | database readiness check |
| GET | `/customers` | list persisted customers |
| GET | `/orders` | list persisted orders |
| GET | `/payments` | list persisted financial transactions |
| GET | `/reconciliation` | calculate reconciliation from persisted data |

The liveness endpoint does not require PostgreSQL. The readiness and data endpoints return HTTP 503 when configuration or database access is unavailable.

The API returns customer contact data and has no authentication. Treat it as a local demonstration service until authentication and authorization are added.

## Dashboard

FastAPI serves a lightweight dashboard at `http://127.0.0.1:8000/dashboard/`,
and the application root redirects there.

Dashboard features include:

- Total orders, net amount paid, outstanding balance, and flagged-order summaries
- Paid, partial, unpaid, and overpaid counts
- Responsive reconciliation table
- Order and customer search
- Financial-status and flagged-order filters
- Discrepancy messages and connection-error handling

The dashboard is plain HTML, CSS, and JavaScript served by the backend. This
keeps the demonstration easy to run without adding a separate Node.js toolchain.

## Docker

Docker Compose starts PostgreSQL and FastAPI, waits for the database health check, initializes missing tables, and stores PostgreSQL data in a named volume. Required database variables fail fast when they are absent.

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open `http://localhost:8000/docs` after startup.

Open `http://localhost:8000/dashboard/` for the dashboard.

Load the sample CSV data and regenerate the mounted output files:

```powershell
docker compose run --rm app python main.py
```

Stop containers while preserving database data:

```powershell
docker compose down
```

Local Python development remains supported without Docker.

## Testing

Install the development dependencies once:

```powershell
python -m pip install -r requirements-dev.txt
```

Run the complete suite:

```powershell
python -m pytest
```

Current result:

```text
52 passed
```

The suite covers:

- Dataset and record validation
- Quarantine behavior and validation messages
- Payment, refund, and adjustment reconciliation
- Full, partial, and overpayment edge cases
- SQLAlchemy models and database constraints
- Transaction rollback and primary-key upsert behavior
- FastAPI endpoints and expected failures
- Complete CSV-to-output pipeline integration

Database and API integration tests use isolated in-memory SQLite databases, so PostgreSQL and Docker are not required to run the standard suite. A live PostgreSQL/Compose smoke test remains a deliberate next step.

Ruff formatting, Ruff linting, and pytest run in [GitHub Actions](.github/workflows/ci.yml) on every push and pull request.

## Engineering decisions

- Structural errors fail fast; isolated record errors are quarantined
- Financial truth comes from transaction amounts, not source status labels
- Refunds are positive source amounts with a negative reconciliation effect
- Financial values are validated and reconciled with `Decimal` values at cent precision
- Valid records are persisted transactionally; invalid records remain explainable CSV artifacts
- PostgreSQL persistence is optional so the original batch workflow stays useful
- ORM, API, validation, reconciliation, and orchestration responsibilities remain separate
- The design avoids repository interfaces, dependency-injection frameworks, and class hierarchies that the current complexity does not justify

## Current limitations and future improvements

- Payments do not yet include transaction dates, so last-payment-date reporting is unavailable
- Schema changes currently require manual migration or database recreation; Alembic would be the next database maturity step
- The read-only API has no authentication, pagination, or authorization and is intended for local demonstration
- API reconciliation currently loads complete tables into Pandas and is best suited to small datasets
- Persistence performs upserts rather than full snapshot synchronization or import history
- Standard tests use SQLite; live PostgreSQL, Docker runtime, and browser behavior are not yet tested in CI
- Docker runtime is verified locally, but full Docker and live PostgreSQL integration are not yet exercised in CI
- Dashboard summaries currently use a fixed USD display currency

## Portfolio summary

Automated business-data validation and reconciliation pipeline that cleans related CSV data, emits explainable quarantine records, reconciles payments, refunds, and adjustments at cent precision, optionally upserts validated data to PostgreSQL, and exposes reporting through FastAPI and a responsive dashboard.
