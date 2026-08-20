# business-data-automation
Python automation tool for validating, reconciling, and reporting business data from CSV and Excel files

## PostgreSQL setup

PostgreSQL is currently an additional persistence foundation. The existing CSV pipeline remains the default application workflow and does not require a database connection.

1. Create a local PostgreSQL database and application user.
2. Install the project dependencies with `python -m pip install -r requirements.txt`.
3. Set the `DATABASE_URL` environment variable using a PostgreSQL connection string:

   ```powershell
   $env:DATABASE_URL = "postgresql://business_data_user:your_password@localhost:5432/business_data_automation"
   ```

4. Initialize the tables from Python:

   ```powershell
   python -c "from app.db.database import initialize_database; initialize_database()"
   ```

The schema creates `customers`, `orders`, and `payments` tables. The `orders.customer_id` and `payments.order_id` foreign keys preserve the same parent-child relationships enforced by the CSV validation pipeline. The database column `orders.order_date` corresponds to the CSV `date` field.

Database credentials are read only from `DATABASE_URL` and are not stored in source code. Pipeline persistence will be connected in a later milestone.
