# business-data-automation
Python automation tool for validating, reconciling, and reporting business data from CSV and Excel files

## PostgreSQL setup

PostgreSQL is an optional persistence layer for validated pipeline records. The existing CSV reports remain available and do not require a database connection.

1. Create a local PostgreSQL database and application user.
2. Install the project dependencies with `python -m pip install -r requirements.txt`.
3. Set the `DATABASE_URL` environment variable using a PostgreSQL connection string:

   ```powershell
   $env:DATABASE_URL = "postgresql+psycopg://business_data_user:your_password@localhost:5432/business_data_automation"
   ```

4. Initialize the tables from Python:

   ```powershell
   python -c "from app.db.database import initialize_database; initialize_database()"
   ```

SQLAlchemy models create the `customers`, `orders`, and `payments` tables. The `orders.customer_id` and `payments.order_id` foreign keys preserve the same parent-child relationships enforced by the CSV validation pipeline. The database column `orders.order_date` corresponds to the CSV `date` field.

Database credentials are read only from `DATABASE_URL` and are not stored in source code. When it is configured, each pipeline run creates any missing tables and saves valid customers, orders, and payments in one transaction. Existing primary keys are updated instead of inserted again, making repeated runs safe from duplicate-key failures. A database failure is logged and rolled back without preventing the CSV reconciliation and quarantine outputs.

Invalid records remain in the existing quarantine CSV files rather than being stored in PostgreSQL. This keeps the normalized tables limited to validated business data while preserving each rejected row and its `validation_errors` value in the format already used by the pipeline.
