from datetime import datetime, timezone


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

    if (
        row["order_id"] in source_paid_order_ids
        and row["financial_status"] in {"unpaid", "partial"}
    ):
        flags.append(
            f"source status says paid but amount is {row['financial_status']}"
        )

    return "; ".join(flags)


def build_report(customers, orders, payments):
    """
    builds a reconciliation report by combining customer, order and payment data
    :param customers: dataframe containing customer information
    :param orders: dataframe containing order information
    :param payments: dataframe containing payment information
    :returns: a dataframe containing the completed reconciliation report
    """
    report = orders.merge( customers, on="customer_id", how="left" )

    payment_summary = payments.groupby("order_id", as_index=False).agg(
        amount_paid=("amount", "sum"),
        payment_count=("amount", "size"),
    )

    report = report.merge(payment_summary, on="order_id", how="left")

    report["amount_paid"] = report["amount_paid"].fillna(0)
    report["payment_count"] = report["payment_count"].fillna(0).astype(int)
    report["balance_due"] = report["total"] - report["amount_paid"]
    report["outstanding_balance"] = report["balance_due"].clip(lower=0)
    report["overpayment_amount"] = (-report["balance_due"]).clip(lower=0)
    report["customer_found"] = report["name"].notna()

    report["financial_status"] = report.apply( lambda row: calculate_financial_status(row["total"], row["amount_paid"],), axis=1, )

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
