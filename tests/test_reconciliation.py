from app.reconciliation.reconcile import calculate_financial_status, build_report
import pandas as pd
import pytest


def test_unpaid_order():
    """
    tests that an order with no payment is unpaid
    :returns: none
    """
    assert calculate_financial_status(100.00, 0.00) == "unpaid"


def test_partial_order():
    """
    tests that a partially paid order is partial
    :returns: none
    """
    assert calculate_financial_status(100.00, 67.00) == "partial"


def test_paid_order():
    """
    tests that a fully paid order is paid
    :returns: none
    """
    assert calculate_financial_status(100.00, 100.00) == "paid"


def test_overpaid_order():
    """
    tests that an overpaid order is overpaid
    :returns: none
    """
    assert calculate_financial_status(100.00, 167.00) == "overpaid"


def test_paid_order_handles_float_precision():
    """
    tests that a paid order handles float precision
    :returns: none
    """
    assert calculate_financial_status(100.00, 99.999999999) == "paid"


def test_build_report_calculates_financial_statuses():
    """
    tests that the report calculates financial statuses
    :returns: none
    """
    customers = pd.DataFrame(
        [
            {
                "customer_id": 1001,
                "name": "John Smith",
                "email": "john@example.com",
                "phone": "(585) 555-1234",
                "email_valid": True,
                "phone_valid": True,
            }
        ]
    )

    orders = pd.DataFrame(
        [
            {
                "order_id": 5001,
                "customer_id": 1001,
                "date": "2026-08-01",
                "total": 100.00,
            },
            {
                "order_id": 5002,
                "customer_id": 1001,
                "date": "2026-08-02",
                "total": 100.00,
            },
            {
                "order_id": 5003,
                "customer_id": 1001,
                "date": "2026-08-03",
                "total": 100.00,
            },
            {
                "order_id": 5004,
                "customer_id": 1001,
                "date": "2026-08-04",
                "total": 100.00,
            },
        ]
    )

    payments = pd.DataFrame(
        [
            {
                "payment_id": 9001,
                "order_id": 5002,
                "amount": 40.00,
                "transaction_type": "payment",
                "status": "partial",
            },
            {
                "payment_id": 9002,
                "order_id": 5003,
                "amount": 60.00,
                "transaction_type": "payment",
                "status": "partial",
            },
            {
                "payment_id": 9003,
                "order_id": 5003,
                "amount": 40.00,
                "transaction_type": "payment",
                "status": "paid",
            },
            {
                "payment_id": 9004,
                "order_id": 5004,
                "amount": 125.00,
                "transaction_type": "payment",
                "status": "paid",
            },
        ]
    )

    report = build_report(customers, orders, payments)

    statuses = dict(
        zip(
            report["order_id"],
            report["financial_status"],
        )
    )

    assert statuses[5001] == "unpaid"
    assert statuses[5002] == "partial"
    assert statuses[5003] == "paid"
    assert statuses[5004] == "overpaid"

    rows = report.set_index("order_id")
    assert rows.loc[5001, "payment_count"] == 0
    assert rows.loc[5001, "outstanding_balance"] == 100.00
    assert rows.loc[5001, "discrepancy_flags"] == "order has no payments"
    assert rows.loc[5004, "overpayment_amount"] == 25.00
    assert rows.loc[5004, "outstanding_balance"] == 0.00
    assert rows.loc[5004, "discrepancy_flags"] == "order is overpaid"
    assert report["reconciliation_timestamp"].nunique() == 1


def test_build_report_aggregates_multiple_payments():
    """
    tests that the report aggregates multiple payments
    :returns: none
    """
    customers = pd.DataFrame(
        [
            {
                "customer_id": 1001,
                "name": "John Smith",
                "email": "john@example.com",
                "phone": "(585) 555-1234",
                "email_valid": True,
                "phone_valid": True,
            }
        ]
    )

    orders = pd.DataFrame(
        [
            {
                "order_id": 5001,
                "customer_id": 1001,
                "date": "2026-08-01",
                "total": 100.00,
            }
        ]
    )

    payments = pd.DataFrame(
        [
            {
                "payment_id": 9001,
                "order_id": 5001,
                "amount": 25.00,
                "transaction_type": "payment",
                "status": "partial",
            },
            {
                "payment_id": 9002,
                "order_id": 5001,
                "amount": 35.00,
                "transaction_type": "payment",
                "status": "partial",
            },
            {
                "payment_id": 9003,
                "order_id": 5001,
                "amount": 40.00,
                "transaction_type": "payment",
                "status": "paid",
            },
        ]
    )

    report = build_report(customers, orders, payments)

    row = report.iloc[0]

    assert row["amount_paid"] == 100.00
    assert row["payment_count"] == 3
    assert row["balance_due"] == 0.00
    assert row["financial_status"] == "paid"


def test_build_report_handles_an_empty_payment_dataset():
    """
    tests that a report with no payment records marks orders as unpaid
    :returns: none
    """
    customers = pd.DataFrame(
        [{"customer_id": 1001, "name": "John Smith"}]
    )
    orders = pd.DataFrame(
        [{"order_id": 5001, "customer_id": 1001, "total": 100.00}]
    )
    payments = pd.DataFrame(
        columns=["payment_id", "order_id", "amount", "transaction_type", "status"]
    )

    report = build_report(customers, orders, payments)

    assert report.iloc[0]["amount_paid"] == 0
    assert report.iloc[0]["payment_count"] == 0
    assert report.iloc[0]["financial_status"] == "unpaid"


def test_build_report_does_not_derive_status_from_source_status():
    """
    tests that financial status is based on amounts rather than source status
    :returns: none
    """
    customers = pd.DataFrame(
        [{"customer_id": 1001, "name": "John Smith"}]
    )
    orders = pd.DataFrame(
        [{"order_id": 5001, "customer_id": 1001, "total": 100.00}]
    )
    payments = pd.DataFrame(
        [
            {
                "payment_id": 9001,
                "order_id": 5001,
                "amount": 100.00,
                "transaction_type": "payment",
                "status": "pending",
            }
        ]
    )

    report = build_report(customers, orders, payments)

    assert report.iloc[0]["financial_status"] == "paid"
    assert report.iloc[0]["discrepancy_flags"] == ""


def test_build_report_flags_paid_source_with_partial_amount():
    """
    tests that a paid source status with a partial amount is flagged
    :returns: none
    """
    customers = pd.DataFrame(
        [{"customer_id": 1001, "name": "John Smith"}]
    )
    orders = pd.DataFrame(
        [{"order_id": 5001, "customer_id": 1001, "total": 100.00}]
    )
    payments = pd.DataFrame(
        [
            {
                "payment_id": 9001,
                "order_id": 5001,
                "amount": 40.00,
                "transaction_type": "payment",
                "status": "paid",
            }
        ]
    )

    report = build_report(customers, orders, payments)

    assert report.iloc[0]["financial_status"] == "partial"
    assert (
        report.iloc[0]["discrepancy_flags"]
        == "source status says paid but amount is partial"
    )


@pytest.mark.parametrize(
    ("transactions", "expected_amount", "expected_status"),
    [
        ([(100.00, "payment"), (100.00, "refund")], 0.00, "unpaid"),
        ([(100.00, "payment"), (40.00, "refund")], 60.00, "partial"),
        ([(80.00, "payment"), (20.00, "refund")], 60.00, "partial"),
        ([(125.00, "payment"), (25.00, "refund")], 100.00, "paid"),
    ],
    ids=["full-refund", "partial-refund", "payment-then-refund", "overpay-refund"],
)
def test_build_report_applies_refunds(
    transactions,
    expected_amount,
    expected_status,
):
    """
    tests that refund transactions reduce the reconciled amount paid
    :param transactions: payment and refund amounts for the order
    :param expected_amount: expected net amount after transactions
    :param expected_status: expected calculated financial status
    :returns: none
    """
    customers = pd.DataFrame(
        [{"customer_id": 1001, "name": "John Smith"}]
    )
    orders = pd.DataFrame(
        [{"order_id": 5001, "customer_id": 1001, "total": 100.00}]
    )
    payments = pd.DataFrame(
        [
            {
                "payment_id": 9001 + index,
                "order_id": 5001,
                "amount": amount,
                "transaction_type": transaction_type,
                "status": "refunded" if transaction_type == "refund" else "paid",
            }
            for index, (amount, transaction_type) in enumerate(transactions)
        ]
    )

    report = build_report(customers, orders, payments)

    assert report.iloc[0]["amount_paid"] == expected_amount
    assert report.iloc[0]["financial_status"] == expected_status


def test_build_report_applies_signed_adjustments():
    """
    tests that adjustment transactions use their signed source amount
    :returns: none
    """
    customers = pd.DataFrame(
        [{"customer_id": 1001, "name": "John Smith"}]
    )
    orders = pd.DataFrame(
        [{"order_id": 5001, "customer_id": 1001, "total": 100.00}]
    )
    payments = pd.DataFrame(
        [
            {
                "payment_id": 9001,
                "order_id": 5001,
                "amount": 100.00,
                "transaction_type": "payment",
                "status": "paid",
            },
            {
                "payment_id": 9002,
                "order_id": 5001,
                "amount": -10.00,
                "transaction_type": "adjustment",
                "status": "partial",
            },
        ]
    )

    report = build_report(customers, orders, payments)

    assert report.iloc[0]["amount_paid"] == 90.00
    assert report.iloc[0]["financial_status"] == "partial"
