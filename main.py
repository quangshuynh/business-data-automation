import logging
from pathlib import Path

import pandas as pd

from app.config import is_database_configured
from app.db.persistence import DatabasePersistenceError, persist_valid_data
from app.reconciliation.reconcile import build_report
from app.validators.validate import (
    is_valid_email,
    normalize_email,
    normalize_name,
    normalize_phone,
    separate_invalid_customers,
    separate_invalid_orders,
    separate_invalid_payments,
    validate_required_columns,
    validate_unique_ids,
)

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def load_data():
    """
    load customer, order, and payment data from CSV files
    :returns: a tuple containing the customers, orders, and payments dataframes
    """
    customers = pd.read_csv(DATA_DIR / "customers.csv")
    orders = pd.read_csv(DATA_DIR / "orders.csv")
    payments = pd.read_csv(DATA_DIR / "payments.csv")
    return customers, orders, payments


def validate_and_clean_data(customers, orders, payments):
    """
    validate required data and clean customer contact information
    :param customers: dataframe containing customer information
    :param orders: dataframe containing order information
    :param payments: dataframe containing payment information
    :returns: a tuple containing the validated and cleaned dataframes
    """
    validate_required_columns(
        customers,  # dataframe
        ["customer_id", "name", "email", "phone"],  # col id
        "customers",  # dataset name
    )

    validate_required_columns(
        orders,
        ["order_id", "customer_id", "date", "total"],
        "orders",
    )

    validate_required_columns(
        payments,
        ["payment_id", "order_id", "amount", "transaction_type", "status"],
        "payments",
    )

    validate_unique_ids(
        customers,
        "customer_id",
        "customers",
    )

    validate_unique_ids(
        orders,
        "order_id",
        "orders",
    )

    validate_unique_ids(
        payments,
        "payment_id",
        "payments",
    )

    customers["name"] = customers["name"].apply(normalize_name)
    customers["email"] = customers["email"].apply(normalize_email)
    customers["phone"] = customers["phone"].apply(normalize_phone)
    customers["email_valid"] = customers["email"].apply(is_valid_email)
    customers["phone_valid"] = customers["phone"].notna()

    # separate valid and invalid info
    valid_customers, invalid_customers = separate_invalid_customers(customers)
    valid_orders, invalid_orders = separate_invalid_orders(
        orders, valid_customers, invalid_customers
    )
    valid_payments, invalid_payments = separate_invalid_payments(
        payments, valid_orders, invalid_orders
    )

    return (
        valid_customers,
        invalid_customers,
        valid_orders,
        invalid_orders,
        valid_payments,
        invalid_payments,
    )


def main():
    """
    runs the reconciliation process and generates the output report
    :returns: process status code
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    try:
        logger.info("loading input data")

        customers, orders, payments = load_data()

        logger.info("validating and cleaning data")

        (
            valid_customers,
            invalid_customers,
            valid_orders,
            invalid_orders,
            valid_payments,
            invalid_payments,
        ) = validate_and_clean_data(
            customers,
            orders,
            payments,
        )

        if is_database_configured():
            logger.info("persisting validated records to PostgreSQL")

            try:
                persisted_counts = persist_valid_data(
                    valid_customers,
                    valid_orders,
                    valid_payments,
                )
                logger.info(
                    "database persistence complete: %s customers, %s orders, %s payments",
                    persisted_counts["customers"],
                    persisted_counts["orders"],
                    persisted_counts["payments"],
                )
            except DatabasePersistenceError as error:
                logger.error("database persistence failed: %s", error)
        else:
            logger.info("database persistence skipped: DATABASE_URL is not configured")

        logger.info("building reconciliation report")

        report = build_report(
            valid_customers,
            valid_orders,
            valid_payments,
        )

        output_path = OUTPUT_DIR / "reconciliation_report.csv"
        report.to_csv(output_path, index=False)

        invalid_customers_path = OUTPUT_DIR / "invalid_customers.csv"
        invalid_customers.to_csv(invalid_customers_path, index=False)

        invalid_orders_path = OUTPUT_DIR / "invalid_orders.csv"
        invalid_orders.to_csv(invalid_orders_path, index=False)

        invalid_payments_path = OUTPUT_DIR / "invalid_payments.csv"
        invalid_payments.to_csv(invalid_payments_path, index=False)

        logger.info(
            "processing complete: %s valid customers, %s invalid customers",
            len(valid_customers),
            len(invalid_customers),
        )

        logger.info(
            "orders: %s valid, %s invalid",
            len(valid_orders),
            len(invalid_orders),
        )

        logger.info(
            "payments: %s valid, %s invalid",
            len(valid_payments),
            len(invalid_payments),
        )

        logger.info(
            "financial statuses: %s unpaid, %s partial, %s paid, %s overpaid",
            (report["financial_status"] == "unpaid").sum(),
            (report["financial_status"] == "partial").sum(),
            (report["financial_status"] == "paid").sum(),
            (report["financial_status"] == "overpaid").sum(),
        )

        logger.info("report generated at %s", output_path)
        return 0

    except ValueError as error:
        logger.error("validation failed: %s", error)
        return 1
    except (OSError, pd.errors.ParserError) as error:
        logger.error("file processing failed: %s", error)
        return 1


# main guard
if __name__ == "__main__":
    raise SystemExit(main())
