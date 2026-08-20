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
