from main import calculate_financial_status


def test_unpaid_order():
    assert calculate_financial_status(100.00, 0.00) == "unpaid"


def test_partial_order():
    assert calculate_financial_status(100.00, 40.00) == "partial"


def test_paid_order():
    assert calculate_financial_status(100.00, 100.00) == "paid"


def test_overpaid_order():
    assert calculate_financial_status(100.00, 125.00) == "overpaid"


def test_paid_order_handles_float_precision():
    assert calculate_financial_status(100.00, 99.999999999) == "paid"