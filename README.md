# business-data-automation
Python automation tool for validating, reconciling, and reporting business data from CSV and Excel files

## PostgreSQL setup

PostgreSQL is an optional persistence layer for validated pipeline records. The existing CSV reports remain available and do not require a database connection.

1. Create a local PostgreSQL database and application user.
2. Install the project dependencies with `python -m pip install -r requirements.txt`.
3. Copy the environment template and replace `change_me` with the local database password:

   ```powershell
   Copy-Item .env.example .env
   ```

   The application automatically loads `.env`. You can instead set `DATABASE_URL` directly in the shell:

   ```powershell
   $env:DATABASE_URL = "postgresql+psycopg://business_data_user:your_password@localhost:5432/business_data_automation"
   ```

4. Run the CSV pipeline with `python main.py`. When `DATABASE_URL` is configured, the pipeline automatically creates missing tables and persists validated records.

   To initialize the tables without running the pipeline, use:

   ```powershell
   python -c "from app.db.database import initialize_database; initialize_database()"
   ```

SQLAlchemy models create the `customers`, `orders`, and `payments` tables. The `orders.customer_id` and `payments.order_id` foreign keys preserve the same parent-child relationships enforced by the CSV validation pipeline. The database column `orders.order_date` corresponds to the CSV `date` field.

Database credentials are read only from `DATABASE_URL` and are not stored in source code. The committed `.env.example` contains placeholders only, while `.env` is excluded by `.gitignore`. `DATABASE_URL` must use the `postgresql+psycopg://` format. When it is configured, each pipeline run creates any missing tables and saves valid customers, orders, and payments in one transaction. Existing primary keys are updated instead of inserted again, making repeated runs safe from duplicate-key failures. A database failure is logged and rolled back without preventing the CSV reconciliation and quarantine outputs.

Invalid records remain in the existing quarantine CSV files rather than being stored in PostgreSQL. This keeps the normalized tables limited to validated business data while preserving each rejected row and its `validation_errors` value in the format already used by the pipeline.

## FastAPI interface

The batch workflow remains available through `python main.py`. With `DATABASE_URL` configured, start the API separately with:

```powershell
uvicorn app.api.api:api --reload
```

Interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs`. The initial read-only API provides:

- `GET /health`
- `GET /customers`
- `GET /orders`
- `GET /payments`
- `GET /reconciliation`

The health endpoint does not require a database connection. Data endpoints return HTTP 503 when database configuration or access is unavailable. Reconciliation results are calculated through the existing reconciliation module rather than duplicated in the API.

## Project structure

Application responsibilities are separated by their actual runtime roles:

- `app/api` contains HTTP routes, dependencies, and response schemas
- `app/db` contains SQLAlchemy models, sessions, and persistence
- `app/reconciliation` contains financial reconciliation rules
- `app/services` coordinates database records with reusable business logic
- `app/validators` contains structural and record-level validation
- `app/config.py` contains environment configuration
- `main.py` remains the CSV batch entry point

The API routes remain thin: persisted reconciliation adaptation lives in `app/services/reconciliation_service.py`, while the underlying calculations remain in `app/reconciliation/reconcile.py`. No repository interfaces or additional class hierarchy are used because the current application does not require them.

## Docker setup

Docker Compose runs the FastAPI application and PostgreSQL together while keeping PostgreSQL data in a named volume.

1. Create the local environment file and replace every `change_me` value:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Build and start the services:

   ```powershell
   docker compose up --build
   ```

3. Open the API documentation at `http://localhost:8000/docs`.

The application container waits for PostgreSQL to pass its health check, initializes missing SQLAlchemy tables, and then starts Uvicorn. PostgreSQL data persists in the `postgres_data` volume.

To load the sample CSV data into PostgreSQL and regenerate the mounted output files while the database is running:

```powershell
docker compose run --rm app python main.py
```

Stop the services with:

```powershell
docker compose down
```

Use `docker compose down --volumes` only when the local PostgreSQL data should also be deleted. Local non-Docker development remains supported through the PostgreSQL, CLI, and Uvicorn commands documented above.

## Testing

Run the full suite with:

```powershell
python -m pytest
```

The suite covers structural validation, record quarantine, reconciliation edge cases, SQLAlchemy models and constraints, idempotent persistence, transaction handling, API endpoints and expected errors, and the complete CSV-to-output pipeline. Database and API integration tests use isolated in-memory databases, so the standard suite does not require PostgreSQL or Docker.

## Reconciliation report

The report derives `financial_status` from the order total and the sum of valid payment amounts. It does not trust the source payment status as the calculated result.

Each reconciled order includes:

- `amount_paid` and the original signed `balance_due`
- non-negative `outstanding_balance` and `overpayment_amount`
- `payment_count`
- `financial_status` with unpaid, partial, paid, or overpaid values
- `discrepancy_flags`
- a UTC `reconciliation_timestamp`

Current discrepancy flags identify orders with no payments, overpaid orders, refunds that exceed payments, and orders where a source payment says paid while the aggregated amount is only unpaid or partial. A last-payment date is intentionally omitted because the current payment input does not contain a transaction date.

## Payment transaction model

Payment input includes a required `transaction_type` that defines the amount's financial effect independently of the source `status`:

- `payment` requires a positive amount and increases the net paid amount
- `refund` requires a positive amount and reduces the net paid amount
- `adjustment` requires a non-zero signed amount and applies that sign directly

Financial reconciliation uses the sum of these signed transaction effects. A full refund therefore returns an order to unpaid, a partial refund reduces it to partial, and an overpayment followed by a sufficient refund can return it to paid. A net amount of zero or less is classified as unpaid.

This milestone adds a required `payments.transaction_type` database column and new check constraints. SQLAlchemy `create_all()` creates the correct structure for new databases but does not migrate an existing table. Existing development databases must be migrated before running the updated pipeline, or recreated when their data is disposable. For Docker development data, recreation is:

```powershell
docker compose down --volumes
docker compose up --build
```
