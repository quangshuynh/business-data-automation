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
