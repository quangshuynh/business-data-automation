import pandas as pd
import pytest
from app.validators.validate import ( separate_invalid_customers, separate_invalid_orders, separate_invalid_payments, validate_required_columns, validate_unique_ids, )


def test_invalid_customer_is_quarantined():
    """
    tests that an invalid customer is quarantined
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
            },
            {
                "customer_id": 1002,
                "name": "Jane Doe",
                "email": "bad-email",
                "phone": "(585) 555-2222",
                "email_valid": False,
                "phone_valid": True,
            },
        ]
    )

    valid_customers, invalid_customers = separate_invalid_customers(customers)

    assert len(valid_customers) == 1
    assert len(invalid_customers) == 1

    invalid_row = invalid_customers.iloc[0]

    assert invalid_row["customer_id"] == 1002
    assert invalid_row["validation_errors"] == "invalid email"


def test_invalid_order_total_is_quarantined():
    """
    tests that an order with an invalid total is quarantined
    :returns: none
    """
    valid_customers = pd.DataFrame(
        [
            {
                "customer_id": 1001,
            }
        ]
    )

    invalid_customers = pd.DataFrame(
        columns=["customer_id"]
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
                "total": -50.00,
            },
        ]
    )

    valid_orders, invalid_orders = separate_invalid_orders(
        orders,
        valid_customers,
        invalid_customers,
    )

    assert len(valid_orders) == 1
    assert len(invalid_orders) == 1

    invalid_row = invalid_orders.iloc[0]

    assert invalid_row["order_id"] == 5002
    assert invalid_row["validation_errors"] == "invalid total"


def test_order_distinguishes_invalid_customer_from_missing_customer():
    """
    tests that orders distinguish invalid customers from missing customers
    :returns: none
    """
    valid_customers = pd.DataFrame(
        [
            {
                "customer_id": 1001,
            }
        ]
    )

    invalid_customers = pd.DataFrame(
        [
            {
                "customer_id": 1002,
            }
        ]
    )

    orders = pd.DataFrame(
        [
            {
                "order_id": 5001,
                "customer_id": 1002,
                "date": "2026-08-01",
                "total": 100.00,
            },
            {
                "order_id": 5002,
                "customer_id": 9999,
                "date": "2026-08-02",
                "total": 100.00,
            },
        ]
    )

    _, invalid_orders = separate_invalid_orders(
        orders,
        valid_customers,
        invalid_customers,
    )

    errors = dict(
        zip(
            invalid_orders["order_id"],
            invalid_orders["validation_errors"],
        )
    )

    assert errors[5001] == "customer failed validation"
    assert errors[5002] == "customer not found"


def test_invalid_payment_is_quarantined():
    """
    tests that an invalid payment is quarantined
    :returns: none
    """
    valid_orders = pd.DataFrame(
        [
            {
                "order_id": 5001,
            }
        ]
    )

    invalid_orders = pd.DataFrame(
        columns=["order_id"]
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
                "amount": -25.00,
                "transaction_type": "payment",
                "status": "paid",
            },
        ]
    )

    valid_payments, invalid_payments = separate_invalid_payments( payments, valid_orders, invalid_orders, )

    assert len(valid_payments) == 1
    assert len(invalid_payments) == 1

    invalid_row = invalid_payments.iloc[0]

    assert invalid_row["payment_id"] == 9002
    assert invalid_row["validation_errors"] == "invalid amount"


def test_payment_transaction_rules_are_validated():
    """
    tests refund adjustment and unsupported transaction type validation
    :returns: none
    """
    valid_orders = pd.DataFrame([{"order_id": 5001}])
    invalid_orders = pd.DataFrame(columns=["order_id"])
    payments = pd.DataFrame(
        [
            {
                "payment_id": 9001,
                "order_id": 5001,
                "amount": 25.00,
                "transaction_type": "refund",
                "status": "refunded",
            },
            {
                "payment_id": 9002,
                "order_id": 5001,
                "amount": -10.00,
                "transaction_type": "adjustment",
                "status": "partial",
            },
            {
                "payment_id": 9003,
                "order_id": 5001,
                "amount": -5.00,
                "transaction_type": "refund",
                "status": "refunded",
            },
            {
                "payment_id": 9004,
                "order_id": 5001,
                "amount": 0.00,
                "transaction_type": "adjustment",
                "status": "partial",
            },
            {
                "payment_id": 9005,
                "order_id": 5001,
                "amount": 10.00,
                "transaction_type": "unknown",
                "status": "paid",
            },
        ]
    )

    valid_payments, invalid_payments = separate_invalid_payments(
        payments,
        valid_orders,
        invalid_orders,
    )
    errors = dict(
        zip(
            invalid_payments["payment_id"],
            invalid_payments["validation_errors"],
        )
    )

    assert valid_payments["payment_id"].tolist() == [9001, 9002]
    assert errors[9003] == "invalid amount"
    assert errors[9004] == "invalid amount"
    assert errors[9005] == "invalid transaction type"


def test_missing_required_column_raises_error():
    """
    tests that a missing required column raises an error
    :returns: none
    """
    customers = pd.DataFrame(
        [
            {
                "customer_id": 1001,
                "name": "John Smith",
                "email": "john@example.com",
            }
        ]
    )

    with pytest.raises(ValueError, match="customers is missing required columns",):
        validate_required_columns(
            customers, # dataframe
            ["customer_id", "name", "email", "phone"], # col id
            "customers", # dataset name
        )


def test_duplicate_ids_raise_error():
    """
    tests that duplicate ids raise an error
    :returns: none
    """
    orders = pd.DataFrame(
        [
            {
                "order_id": 5001,
                "customer_id": 1001,
                "date": "2026-08-01",
                "total": 100.00,
            },
            {
                "order_id": 5001,
                "customer_id": 1002,
                "date": "2026-08-02",
                "total": 75.00,
            },
        ]
    )

    with pytest.raises(
        ValueError,
        match="orders contains duplicate order_id values",
    ):
        validate_unique_ids(
            orders,
            "order_id",
            "orders",
        )


def test_customer_can_have_multiple_validation_errors():
    """
    tests that a customer can have multiple validation errors
    :returns: none
    """
    customers = pd.DataFrame(
        [
            {
                "customer_id": 1001,
                "name": None,
                "email": "bad-email",
                "phone": None,
                "email_valid": False,
                "phone_valid": False,
            }
        ]
    )

    _, invalid_customers = separate_invalid_customers(customers)

    invalid_row = invalid_customers.iloc[0]

    assert ( invalid_row["validation_errors"] == "missing name; invalid email; invalid phone" )
