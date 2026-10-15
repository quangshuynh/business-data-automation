from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def calculate_financial_status(order_total, amount_paid):
    """
    calculates an order's financial status based on the order total and amount paid
    :param order_total: total amount due for the order
    :param amount_paid: total amount paid toward the order
    :returns: calculated financial status
    """
    order_total = round_financial_amount(order_total)
    amount_paid = round_financial_amount(amount_paid)

    if amount_paid <= 0:
        return "unpaid"

    if amount_paid < order_total:
        return "partial"

    if amount_paid == order_total:
        return "paid"

    return "overpaid"


def calculate_transaction_amount(amount, transaction_type):
    """
    calculates the signed financial effect of a payment transaction
    :param amount: transaction amount from the source record
    :param transaction_type: payment refund or adjustment transaction type
    :returns: signed amount used for reconciliation
    """
    normalized_amount = round_financial_amount(amount)

    if transaction_type == "refund":
        return -normalized_amount

    return normalized_amount


def round_financial_amount(amount):
    """
    rounds a financial amount to two decimal places
    :param amount: financial amount to round
    :returns: amount rounded to two decimal places
    """
    rounded_amount = Decimal(str(amount)).quantize(CENT, rounding=ROUND_HALF_UP)
    return Decimal("0.00") if rounded_amount == 0 else rounded_amount


def get_discrepancy_flags(row, source_paid_order_ids):
    """
    returns business discrepancies identified for a reconciled order
    :param row: reconciliation report row
    :param source_paid_order_ids: order ids with a source payment marked paid
    :returns: semicolon separated string containing discrepancy flags
    """
    flags = []

    if row["payment_count"] == 0:
        flags.append("order has no payments")

    if row["financial_status"] == "overpaid":
        flags.append("order is overpaid")

    if row["amount_paid"] < 0:
        flags.append("net transaction amount is negative")

    if row["order_id"] in source_paid_order_ids and row["financial_status"] in {
        "unpaid",
        "partial",
    }:
        flags.append(f"source status says paid but amount is {row['financial_status']}")

    return "; ".join(flags)


def ensure_unique_ids(frame, id_column, dataset_name):
    """
    guards against identifiers that would be counted twice by a merge
    :param frame: dataframe passed to the report builder
    :param id_column: identifier column that must be unique
    :param dataset_name: dataset name used in the error message
    :returns: none
    """
    if id_column not in frame.columns:
        return

    identifiers = frame[id_column].dropna()
    duplicates = sorted(set(identifiers[identifiers.duplicated()]))

    if duplicates:
        raise ValueError(
            f"{dataset_name} contain duplicate {id_column} values {duplicates}; "
            "reconciliation would count them more than once"
        )


def build_report(customers, orders, payments):
    """
    builds a reconciliation report by combining customer, order and payment data
    :param customers: dataframe containing customer information
    :param orders: dataframe containing order information
    :param payments: dataframe containing payment information
    :returns: a dataframe containing the completed reconciliation report
    """
    ensure_unique_ids(customers, "customer_id", "customers")
    ensure_unique_ids(orders, "order_id", "orders")
    ensure_unique_ids(payments, "payment_id", "payments")

    order_columns = [
        column
        for column in ["order_id", "customer_id", "date", "total"]
        if column in orders.columns
    ]
    customer_columns = [
        column
        for column in ["customer_id", "name", "email", "phone"]
        if column in customers.columns
    ]
    payment_columns = [
        "payment_id",
        "order_id",
        "amount",
        "transaction_type",
        "status",
    ]

    report = orders[order_columns].merge(
        customers[customer_columns],
        on="customer_id",
        how="left",
        indicator="_customer_match",
    )
    report["total"] = report["total"].apply(round_financial_amount)

    payment_transactions = payments[payment_columns].copy()
    payment_transactions["transaction_amount"] = payment_transactions.apply(
        lambda row: calculate_transaction_amount(
            row["amount"],
            row["transaction_type"],
        ),
        axis=1,
    )

    payment_summary = payment_transactions.groupby("order_id", as_index=False).agg(
        amount_paid=("transaction_amount", "sum"),
        payment_count=("amount", "size"),
    )

    report = report.merge(payment_summary, on="order_id", how="left")

    report["amount_paid"] = (
        report["amount_paid"].fillna(0).apply(round_financial_amount)
    )
    report["payment_count"] = report["payment_count"].fillna(0).astype(int)
    report["balance_due"] = (report["total"] - report["amount_paid"]).apply(
        round_financial_amount
    )
    report["outstanding_balance"] = (
        report["balance_due"].clip(lower=0).apply(round_financial_amount)
    )
    report["overpayment_amount"] = (
        (-report["balance_due"]).clip(lower=0).apply(round_financial_amount)
    )
    # a matched customer may legitimately have a blank optional name
    report["customer_found"] = report.pop("_customer_match") == "both"

    report["financial_status"] = report.apply(
        lambda row: calculate_financial_status(
            row["total"],
            row["amount_paid"],
        ),
        axis=1,
    )

    source_paid_order_ids = set(
        payments.loc[
            payments["status"].astype(str).str.strip().str.lower() == "paid",
            "order_id",
        ]
    )
    report["discrepancy_flags"] = report.apply(
        get_discrepancy_flags,
        axis=1,
        args=(source_paid_order_ids,),
    )
    report["reconciliation_timestamp"] = datetime.now(timezone.utc)

    return report
