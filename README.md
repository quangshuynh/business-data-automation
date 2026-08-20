# Business Data Automation

A tested Python data pipeline that validates incoming customer, order, and payment CSV files, quarantines invalid records, reconciles financial balances, persists validated data to PostgreSQL, and exposes results through FastAPI.

The project models a realistic back-office automation problem: business data arrives from multiple files, individual records may be malformed or reference invalid parents, and source payment labels cannot be trusted as the final financial truth.

## What the system does

- Loads customer, order, and payment CSV datasets
- Treats missing columns and duplicate primary IDs as fatal structural failures
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

Invalid records remain in CSV quarantine files rather than PostgreSQL. This keeps normalized tables limited to validated data while preserving each rejected row and its `validation_errors` explanation.

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
- Refunds that exceed payments
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

The generated files are:

```text
output/reconciliation_report.csv
output/invalid_customers.csv
output/invalid_orders.csv
output/invalid_payments.csv
```

## Quick start: CSV workflow

Prerequisites:

- Python 3.14 or a compatible modern Python version
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
| GET | `/health` | application health check |
| GET | `/customers` | list persisted customers |
| GET | `/orders` | list persisted orders |
| GET | `/payments` | list persisted financial transactions |
| GET | `/reconciliation` | calculate reconciliation from persisted data |

The health endpoint does not require PostgreSQL. Database-backed endpoints return HTTP 503 when configuration or database access is unavailable.

## Dashboard

FastAPI serves a lightweight dashboard at `http://127.0.0.1:8000/dashboard/`, and the application root redirects there. The dashboard uses the existing reconciliation endpoint and adds no duplicate financial calculations.

Dashboard features include:

- Total orders, net amount paid, outstanding balance, and flagged-order summaries
- Paid, partial, unpaid, and overpaid counts
- Responsive reconciliation table
- Order and customer search
- Financial-status and flagged-order filters
- Discrepancy messages and connection-error handling

The dashboard is plain HTML, CSS, and JavaScript served by the backend. This keeps the demonstration easy to run without adding a separate Node.js toolchain.

## Docker

Docker Compose starts PostgreSQL and FastAPI, waits for the database health check, initializes missing tables, and stores PostgreSQL data in a named volume.

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open `http://localhost:8000/docs` after startup.

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

Run the complete suite:

```powershell
python -m pytest
```

Current result:

```text
41 passed
```

The suite covers:

- Dataset and record validation
- Quarantine behavior and validation messages
- Payment, refund, and adjustment reconciliation
- Full, partial, and overpayment edge cases
- SQLAlchemy models and database constraints
- Transaction rollback and idempotent persistence
- FastAPI endpoints and expected failures
- Complete CSV-to-output pipeline integration

Database and API integration tests use isolated in-memory databases, so PostgreSQL and Docker are not required to run the standard suite.

## Engineering decisions

- Structural errors fail fast; isolated record errors are quarantined
- Financial truth comes from transaction amounts, not source status labels
- Refunds are positive source amounts with a negative reconciliation effect
- Valid records are persisted transactionally; invalid records remain explainable CSV artifacts
- PostgreSQL persistence is optional so the original batch workflow stays useful
- ORM, API, validation, reconciliation, and orchestration responsibilities remain separate
- The design avoids repository interfaces, dependency-injection frameworks, and class hierarchies that the current complexity does not justify

## Current limitations and future improvements

- Payments do not yet include transaction dates, so last-payment-date reporting is unavailable
- Schema changes currently require manual migration or database recreation; Alembic would be the next database maturity step
- The API is read-only and has no authentication
- Docker configuration should be runtime-verified on a machine with Docker available
- Dashboard summaries currently use a fixed USD display currency

## Portfolio summary

Automated business-data validation and reconciliation pipeline that cleans incoming CSV data, quarantines invalid records, reconciles payments and refunds against orders, persists validated data to PostgreSQL, and exposes tested reporting through FastAPI and Docker.
