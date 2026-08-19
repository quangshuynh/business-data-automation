from pathlib import Path
import pandas as pd
from app.validators.validate import (is_valid_email, normalize_email, normalize_phone, validate_positive_amounts, validate_required_columns, validate_unique_ids, )


DATA_DIR = Path("data") #src/data
OUTPUT_DIR = Path("output") #src/output


def load_data():
    """
    load customer, order, and payment data from CSV files
    :returns: a tuple containing the customers, orders, and payments dataframes
    """
    customers = pd.read_csv(DATA_DIR / "customers.csv")
    orders = pd.read_csv(DATA_DIR / "orders.csv")
    payments = pd.read_csv(DATA_DIR / "payments.csv")
    return customers, orders, payments


def build_report(customers, orders, payments):
    """
    builds a reconciliation report by combining customer, order, and payment data
    :param customers: dataframe containing customer information
    :param orders: dataframe containing order information
    :param payments: dataframe containing payment information
    :returns: a dataframe containing the completed reconciliation report
    """
    report = orders.merge( customers, on="customer_id", how="left" )

    payment_totals = ( payments.groupby("order_id", as_index=False)["amount"].sum().rename(columns={"amount": "amount_paid"}) )

    report = report.merge( payment_totals, on="order_id", how="left" )

    report["amount_paid"] = report["amount_paid"].fillna(0)
    report["balance_due"] = report["total"] - report["amount_paid"]
    report["customer_found"] = report["name"].notna()
    report["payment_status"] = report["balance_due"].apply( lambda balance: "paid" if balance <= 0 else "unpaid_or_partial" )

    return report

def validate_and_clean_data(customers, orders, payments):
    """
    validate required data and clean customer contact information
    :param customers: dataframe containing customer information
    :param orders: dataframe containing order information
    :param payments: dataframe containing payment information
    :returns: a tuple containing the validated and cleaned dataframes
    """
    validate_required_columns(
        customers, #dataframe
        ["customer_id", "name", "email", "phone"], #col id
        "customers", # dataset name
    )

    validate_required_columns(
        orders,
        ["order_id", "customer_id", "date", "total"],
        "orders",
    )

    validate_required_columns(
        payments,
        ["payment_id", "order_id", "amount", "status"],
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

    validate_positive_amounts(
        orders,
        "total",
        "orders",
    )

    validate_positive_amounts(
        payments,
        "amount",
        "payments",
    )

    customers["email"] = customers["email"].apply(normalize_email)
    customers["phone"] = customers["phone"].apply(normalize_phone)
    customers["email_valid"] = customers["email"].apply(is_valid_email)
    customers["phone_valid"] = customers["phone"].notna()

    return customers, orders, payments


def main():
    """
    runs the reconciliation process and generate the output report
    :returns: None
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    customers, orders, payments = load_data()
    report = build_report(customers, orders, payments)

    output_path = OUTPUT_DIR / "reconciliation_report.csv" #output file
    report.to_csv(output_path, index=False)

    print(f"Customers processed: {len(customers)}")
    print(f"Orders processed: {len(orders)}")
    print(f"Payments processed: {len(payments)}")
    print(
        f"Orders with missing customers: "
        f"{(~report['customer_found']).sum()}"
    )
    print(
        f"Unpaid or partial orders: "
        f"{(report['payment_status'] == 'unpaid_or_partial').sum()}"
    )
    print(f"Report generated: {output_path}")


#main guard
if __name__ == "__main__":
    main()