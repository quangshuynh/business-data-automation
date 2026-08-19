from pathlib import Path
import pandas as pd
from app.validators.validate import (is_valid_email, normalize_email, normalize_phone, validate_required_columns, validate_unique_ids, separate_invalid_customers, separate_invalid_orders, separate_invalid_payments)


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


def calculate_financial_status(order_total, amount_paid):
    """
    calculates an order's financial status based on the order total and amount paid
    :param order_total: total amount due for the order
    :param amount_paid: total amount paid toward the order
    :returns: calculated financial status
    """
    order_total = round(order_total, 2)
    amount_paid = round(amount_paid, 2)

    if amount_paid == 0:
        return "unpaid"

    if amount_paid < order_total:
        return "partial"

    if amount_paid == order_total:
        return "paid"

    return "overpaid"


def build_report(customers, orders, payments):
    """
    builds a reconciliation report by combining customer, order and payment data
    :param customers: dataframe containing customer information
    :param orders: dataframe containing order information
    :param payments: dataframe containing payment information
    :returns: a dataframe containing the completed reconciliation report
    """
    report = orders.merge( customers, on="customer_id", how="left" )

    payment_totals = ( payments.groupby("order_id", as_index=False)["amount"].sum().rename(columns={"amount": "amount_paid"}) )

    report = report.merge(payment_totals, on="order_id", how="left")

    report["amount_paid"] = report["amount_paid"].fillna(0)
    report["balance_due"] = report["total"] - report["amount_paid"]
    report["customer_found"] = report["name"].notna()

    report["financial_status"] = report.apply( lambda row: calculate_financial_status(row["total"], row["amount_paid"],), axis=1, )

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

    customers["email"] = customers["email"].apply(normalize_email)
    customers["phone"] = customers["phone"].apply(normalize_phone)
    customers["email_valid"] = customers["email"].apply(is_valid_email)
    customers["phone_valid"] = customers["phone"].notna()

    # separate valid and invalid info
    valid_customers, invalid_customers = separate_invalid_customers(customers)
    valid_orders, invalid_orders = separate_invalid_orders(orders, valid_customers, invalid_customers)
    valid_payments, invalid_payments = separate_invalid_payments(payments, valid_orders, invalid_orders)

    return valid_customers, invalid_customers, valid_orders, invalid_orders, valid_payments, invalid_payments


def main():
    """
    runs the reconciliation process and generate the output report
    :returns: None
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    customers, orders, payments = load_data() # load
    valid_customers, invalid_customers, valid_orders, invalid_orders, valid_payments, invalid_payments = validate_and_clean_data(customers, orders, payments) # validate and clean
    
    report = build_report(valid_customers, valid_orders, valid_payments) # build report

    output_path = OUTPUT_DIR / "reconciliation_report.csv" #output file
    report.to_csv(output_path, index=False)

    invalid_customers_path = OUTPUT_DIR / "invalid_customers.csv"
    invalid_customers.to_csv(invalid_customers_path, index=False)

    invalid_orders_path = OUTPUT_DIR / "invalid_orders.csv"
    invalid_orders.to_csv(invalid_orders_path, index=False)

    invalid_payments_path = OUTPUT_DIR / "invalid_payments.csv"
    invalid_payments.to_csv(invalid_payments_path, index=False)

    print(f"Customers processed: {len(customers)}")
    print(f"Valid customers: {len(valid_customers)}")
    print(f"Invalid customers: {len(invalid_customers)}")
    print(f"Valid orders: {len(valid_orders)}")
    print(f"Invalid orders: {len(invalid_orders)}")
    print(f"Valid payments: {len(valid_payments)}")
    print(f"Invalid payments: {len(invalid_payments)}")
    print(
        f"Orders with missing customers: "
        f"{(~report['customer_found']).sum()}"
    )
    print(
        f"Unpaid orders: "
        f"{(report['financial_status'] == 'unpaid').sum()}"
    )
    print(
        f"Partial orders: "
        f"{(report['financial_status'] == 'partial').sum()}"
    )
    print(
        f"Paid orders: "
        f"{(report['financial_status'] == 'paid').sum()}"
    )
    print(
        f"Overpaid orders: "
        f"{(report['financial_status'] == 'overpaid').sum()}"
    )
    print(f"Report generated: {output_path}")
    print(f"Invalid customer records: {invalid_customers_path}")
    print(f"Invalid order records: {invalid_orders_path}")
    print(f"Invalid payment records: {invalid_payments_path}")


#main guard
if __name__ == "__main__":
    main()