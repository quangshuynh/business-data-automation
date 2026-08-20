from main import calculate_financial_status, build_report
import pandas as pd


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
                "status": "partial",
            },
            {
                "payment_id": 9002,
                "order_id": 5003,
                "amount": 60.00,
                "status": "partial",
            },
            {
                "payment_id": 9003,
                "order_id": 5003,
                "amount": 40.00,
                "status": "paid",
            },
            {
                "payment_id": 9004,
                "order_id": 5004,
                "amount": 125.00,
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
                "status": "partial",
            },
            {
                "payment_id": 9002,
                "order_id": 5001,
                "amount": 35.00,
                "status": "partial",
            },
            {
                "payment_id": 9003,
                "order_id": 5001,
                "amount": 40.00,
                "status": "paid",
            },
        ]
    )

    report = build_report(customers, orders, payments)

    row = report.iloc[0]

    assert row["amount_paid"] == 100.00
    assert row["balance_due"] == 0.00
    assert row["financial_status"] == "paid"