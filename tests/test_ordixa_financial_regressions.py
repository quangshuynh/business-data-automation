"""
financial-correctness regressions for the Ordixa import path

every expected amount below is worked out by hand in the test's docstring or
comments rather than produced by the application
"""

from decimal import Decimal

import pandas as pd
import pytest
from ordixa_helpers import (
    ORDER_HEADER,
    PAYMENT_HEADER,
    build_profile,
    issue_codes,
    write_exports,
    write_rows,
)

from app.ordixa.pipeline import process
from app.reconciliation.reconcile import build_report

D = Decimal


def order(ref, total, customer="7000101", day="2026-08-01"):
    """
    builds one order row in the Harbor Lane storefront layout
    :param ref: order name such as #3001
    :param total: total as written in the export
    :param customer: customer id text
    :param day: order date
    :returns: list of cells
    """
    return [ref, day, customer, "USD", total]


def payment(ref, order_ref, amount, kind="Payment", status="Paid", day="08/02/2026"):
    """
    builds one payment row in the Harbor Lane processor layout
    :param ref: transaction id such as PMT-1
    :param order_ref: order reference such as #3001
    :param amount: amount as written in the export
    :param kind: transaction type label
    :param status: status label
    :param day: payment date
    :returns: list of cells
    """
    return [ref, order_ref, day, kind, status, amount, "USD"]


def customer(identifier, first="Avery", last="Quinn", email="a@example.com"):
    """
    builds one customer row
    :param identifier: customer id text
    :param first: first name
    :param last: last name
    :param email: email address
    :returns: list of cells
    """
    return [identifier, first, last, email, "555-010-0101"]


def ledger(result):
    """
    indexes the ledger by the order reference as exported
    :param result: run result
    :returns: dataframe indexed by order_ref
    """
    return result.ledger.set_index("order_ref")


# customer relationship semantics


def test_customer_without_name_is_still_found(tmp_path):
    """
    a matched customer whose optional name is blank is still on file
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = write_exports(
        tmp_path / "in",
        orders=[order("#3001", "40.00", customer="7000104")],
        payments=[payment("PMT-1", "#3001", "$40.00")],
        customers=[customer("7000104", first="", last="")],
    )

    result = process(build_profile(), input_dir)
    row = ledger(result).loc["#3001"]

    assert row["customer_found"]
    assert row["customer_name"] is None
    assert issue_codes(result, "7000104") == ["missing_name"]
    assert issue_codes(result, "#3001") == []
    assert row["financial_status"] == "paid"


def test_engine_name_does_not_prove_customer_relationship():
    """
    a populated name on some other customer row never marks an unmatched order
    as having a customer on file, and a null name never hides a real match
    :returns: none
    """
    customers = pd.DataFrame(
        [
            {"customer_id": 1, "name": "Avery Quinn", "email": None, "phone": None},
            {"customer_id": 2, "name": None, "email": None, "phone": None},
        ]
    )
    orders = pd.DataFrame(
        [
            {"order_id": 10, "customer_id": 9, "date": "2026-08-01", "total": D("5")},
            {"order_id": 11, "customer_id": 2, "date": "2026-08-01", "total": D("5")},
        ]
    )
    payments = pd.DataFrame(
        columns=["payment_id", "order_id", "amount", "transaction_type", "status"]
    )

    report = build_report(customers, orders, payments).set_index("order_id")

    assert not report.loc[10, "customer_found"]
    assert report.loc[11, "customer_found"]
    assert pd.isna(report.loc[11, "name"])


def test_missing_contact_details_do_not_suppress_money(tmp_path):
    """
    blank email and phone are warnings; the order and payment still count
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = write_exports(
        tmp_path / "in",
        orders=[order("#3001", "120.00", customer="7000150")],
        payments=[payment("PMT-1", "#3001", "$120.00")],
        customers=[["7000150", "Riley", "Stone", "", ""]],
    )

    result = process(build_profile(), input_dir)

    assert issue_codes(result, "7000150") == ["missing_email", "missing_phone"]
    assert result.summary["net_received"] == D("120.00")
    assert ledger(result).loc["#3001", "customer_found"]


@pytest.mark.parametrize("severity", ["warning", "error"])
def test_missing_customer_relationship_follows_profile(tmp_path, severity):
    """
    an order whose customer is absent from the customers file stays visible as
    a warning (and is reconciled) or an error (and is rejected with its payment)
    :param tmp_path: pytest temporary directory
    :param severity: profile missing_customer setting
    :returns: none
    """
    input_dir = write_exports(
        tmp_path / "in",
        orders=[order("#3001", "10.00", customer="7000999")],
        payments=[payment("PMT-1", "#3001", "$10.00")],
        customers=[customer("7000101")],
    )
    profile = build_profile(
        lambda d: d["reconciliation"].update(missing_customer=severity)
    )

    result = process(profile, input_dir)

    assert issue_codes(result, "#3001") == ["customer_not_found"]
    if severity == "warning":
        assert not ledger(result).loc["#3001", "customer_found"]
        assert result.summary["net_received"] == D("10.00")
    else:
        assert result.ledger.empty
        assert issue_codes(result, "PMT-1") == ["order_rejected"]
        assert result.summary["net_received"] == D("0.00")


# duplicates


def test_identical_payment_in_two_files_is_counted_once(tmp_path):
    """
    the same transaction exported in both monthly files counts once:
    order 80.00, one 80.00 payment -> paid, net 80.00 (not 160.00)
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = write_exports(
        tmp_path / "in",
        orders=[order("#3001", "80.00")],
        payments=[payment("PMT-1", "#3001", "$80.00")],
    )
    write_rows(
        input_dir / "payments_copy.csv",
        PAYMENT_HEADER,
        [payment("PMT-1", "#3001", "$80.00")],
    )

    result = process(build_profile(), input_dir)

    assert result.summary["net_received"] == D("80.00")
    assert ledger(result).loc["#3001", "financial_status"] == "paid"
    assert issue_codes(result, "PMT-1") == ["duplicate_row"]


def test_order_repeated_identically_in_two_periods_is_counted_once(tmp_path):
    """
    an order present unchanged in the August and September exports is one order
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = write_exports(
        tmp_path / "in",
        orders=[order("#3001", "50.00")],
        payments=[payment("PMT-1", "#3001", "$50.00")],
    )
    write_rows(
        input_dir / "orders_2026-09.csv", ORDER_HEADER, [order("#3001", "50.00")]
    )

    result = process(build_profile(), input_dir)

    assert len(result.ledger) == 1
    assert result.summary["order_value"] == D("50.00")
    assert issue_codes(result, "#3001") == ["duplicate_row"]


def test_order_changed_between_periods_is_quarantined(tmp_path):
    """
    the same order id with different totals in two periods cannot be resolved
    safely: both copies and the dependent payment are rejected, nothing counts
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = write_exports(
        tmp_path / "in",
        orders=[order("#3001", "50.00")],
        payments=[payment("PMT-1", "#3001", "$50.00")],
    )
    write_rows(
        input_dir / "orders_2026-09.csv", ORDER_HEADER, [order("#3001", "55.00")]
    )

    result = process(build_profile(), input_dir)

    assert result.ledger.empty
    assert issue_codes(result, "#3001") == ["conflicting_duplicate_id"] * 2
    assert issue_codes(result, "PMT-1") == ["order_rejected"]
    assert result.summary["order_value"] == D("0.00")
    assert result.summary["net_received"] == D("0.00")


def test_conflicting_transaction_types_for_one_id_are_rejected(tmp_path):
    """
    one transaction id exported once as a payment and once as a refund is
    ambiguous; neither row may move the balance
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = write_exports(
        tmp_path / "in",
        orders=[order("#3001", "30.00")],
        payments=[
            payment("PMT-1", "#3001", "$30.00"),
            payment("PMT-1", "#3001", "-$30.00", kind="Refund", status="Refunded"),
        ],
    )
    profile = build_profile()

    result = process(profile, input_dir)

    assert issue_codes(result, "PMT-1") == ["conflicting_duplicate_id"] * 2
    assert ledger(result).loc["#3001", "net_paid"] == D("0.00")
    assert ledger(result).loc["#3001", "financial_status"] == "unpaid"


def test_conflicting_customer_records_do_not_block_money(tmp_path):
    """
    two different customer rows with one id are both rejected; the order is
    reconciled with a customer_rejected warning
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = write_exports(
        tmp_path / "in",
        orders=[order("#3001", "25.00", customer="7000101")],
        payments=[payment("PMT-1", "#3001", "$25.00")],
        customers=[
            customer("7000101", email="a@example.com"),
            customer("7000101", email="different@example.com"),
        ],
    )

    result = process(build_profile(), input_dir)
    row = ledger(result).loc["#3001"]

    assert issue_codes(result, "7000101") == ["conflicting_duplicate_id"] * 2
    assert issue_codes(result, "#3001") == ["customer_rejected"]
    assert not row["customer_found"]
    assert row["net_paid"] == D("25.00")


def test_distinct_transactions_with_identical_amounts_both_count(tmp_path):
    """
    two installments of 50.00 with different transaction ids are legitimate
    repeated events: 50.00 + 50.00 = 100.00 settles a 100.00 order
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = write_exports(
        tmp_path / "in",
        orders=[order("#3001", "100.00")],
        payments=[
            payment("PMT-1", "#3001", "$50.00"),
            payment("PMT-2", "#3001", "$50.00"),
        ],
    )

    result = process(build_profile(), input_dir)
    row = ledger(result).loc["#3001"]

    assert row["net_paid"] == D("100.00")
    assert row["transaction_count"] == 2
    assert row["financial_status"] == "paid"
    assert result.issues == []


# amounts and statuses


def test_partial_overpaid_refunded_and_adjusted_orders(tmp_path):
    """
    hand-computed:
      #3001 total 100.00, paid 40.00               -> partial, outstanding 60.00
      #3002 total  20.00, paid 25.00               -> overpaid by 5.00
      #3003 total  60.00, paid 60.00, refund 15.00 -> net 45.00, partial
      #3004 total  10.00, paid 12.00, adj -2.00    -> net 10.00, paid
    net received = 40 + 25 + 45 + 10 = 120.00
    outstanding  = 60 + 15 = 75.00; overpaid = 5.00
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = write_exports(
        tmp_path / "in",
        orders=[
            order("#3001", "100.00"),
            order("#3002", "20.00"),
            order("#3003", "60.00"),
            order("#3004", "10.00"),
        ],
        payments=[
            payment("PMT-1", "#3001", "$40.00", status="Partially Paid"),
            payment("PMT-2", "#3002", "$25.00"),
            payment("PMT-3", "#3003", "$60.00"),
            payment("PMT-4", "#3003", "-$15.00", kind="Refund", status="Refunded"),
            payment("PMT-5", "#3004", "$12.00"),
            payment("PMT-6", "#3004", "($2.00)", kind="Adjustment"),
        ],
    )

    result = process(build_profile(), input_dir)
    rows = ledger(result)

    assert rows.loc["#3001", "financial_status"] == "partial"
    assert rows.loc["#3002", "overpayment_amount"] == D("5.00")
    assert rows.loc["#3003", "refunds"] == D("15.00")
    assert rows.loc["#3003", "net_paid"] == D("45.00")
    assert rows.loc["#3004", "adjustments"] == D("-2.00")
    assert rows.loc["#3004", "financial_status"] == "paid"
    assert result.summary["net_received"] == D("120.00")
    assert result.summary["outstanding_balance"] == D("75.00")
    assert result.summary["overpayments"] == D("5.00")


def test_zero_value_rows_are_rejected_with_reasons(tmp_path):
    """
    a zero order total and a zero payment are rejected rather than counted
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = write_exports(
        tmp_path / "in",
        orders=[order("#3001", "0.00"), order("#3002", "10.00")],
        payments=[payment("PMT-1", "#3002", "$0.00")],
    )

    result = process(build_profile(), input_dir)

    assert issue_codes(result, "#3001") == ["non_positive_total"]
    assert issue_codes(result, "PMT-1") == ["invalid_transaction_amount"]
    assert ledger(result).loc["#3002", "financial_status"] == "unpaid"


def test_amounts_at_the_supported_limit_sum_exactly(tmp_path):
    """
    two orders at the 9,999,999,999.99 limit sum to 19,999,999,999.98 exactly;
    one cent more is rejected as out of range
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = write_exports(
        tmp_path / "in",
        orders=[
            order("#3001", "9,999,999,999.99"),
            order("#3002", "9,999,999,999.99"),
            order("#3003", "10,000,000,000.00"),
        ],
        payments=[
            payment("PMT-1", "#3001", "$9,999,999,999.99"),
            payment("PMT-2", "#3002", "$0.01"),
        ],
    )

    result = process(build_profile(), input_dir)

    assert issue_codes(result, "#3003") == ["amount_out_of_range"]
    assert result.summary["order_value"] == D("19999999999.98")
    assert result.summary["net_received"] == D("10000000000.00")
    assert result.summary["outstanding_balance"] == D("9999999999.98")


def test_sub_cent_amounts_are_rejected_not_rounded(tmp_path):
    """
    0.005 is never silently rounded to 0.01 or 0.00
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = write_exports(
        tmp_path / "in",
        orders=[order("#3001", "10.005")],
        payments=[payment("PMT-1", "#3001", "$10.005")],
    )

    result = process(build_profile(), input_dir)

    assert issue_codes(result, "#3001") == ["too_many_decimal_places"]
    assert "too_many_decimal_places" in issue_codes(result, "PMT-1")


def test_unknown_status_and_missing_order_are_blocking(tmp_path):
    """
    an unmapped status label and a payment for an order that is not in the run
    are both rejected with explicit reasons
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = write_exports(
        tmp_path / "in",
        orders=[order("#3001", "10.00")],
        payments=[
            payment("PMT-1", "#3001", "$10.00", status="Settled-ish"),
            payment("PMT-2", "#3999", "$10.00"),
        ],
    )

    result = process(build_profile(), input_dir)

    assert issue_codes(result, "PMT-1") == ["unmapped_status"]
    assert issue_codes(result, "PMT-2") == ["order_not_in_run"]
    assert result.summary["net_received"] == D("0.00")


# cross-run limitation


def test_payments_cannot_match_orders_from_an_earlier_run(tmp_path):
    """
    documents the single-run boundary: a September payment for an August order
    is rejected when the runs are processed separately, and reconciles only
    when both periods' orders are supplied to the same run
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    august = write_exports(
        tmp_path / "august",
        orders=[order("#3001", "100.00")],
        payments=[payment("PMT-1", "#3001", "$60.00", status="Partially Paid")],
    )
    september = write_exports(
        tmp_path / "september",
        orders=[order("#3002", "5.00", day="2026-09-01")],
        payments=[payment("PMT-2", "#3001", "$40.00", day="09/03/2026")],
    )
    profile = build_profile()

    first = process(profile, august)
    second = process(profile, september)

    assert ledger(first).loc["#3001", "outstanding_balance"] == D("40.00")
    assert issue_codes(second, "PMT-2") == ["order_not_in_run"]
    assert "#3001" not in ledger(second).index
    assert second.summary["net_received"] == D("0.00")

    combined = tmp_path / "combined"
    write_rows(combined / "orders_08.csv", ORDER_HEADER, [order("#3001", "100.00")])
    write_rows(
        combined / "payments_08.csv",
        PAYMENT_HEADER,
        [payment("PMT-1", "#3001", "$60.00", status="Partially Paid")],
    )
    write_rows(
        combined / "payments_09.csv",
        PAYMENT_HEADER,
        [payment("PMT-2", "#3001", "$40.00", day="09/03/2026")],
    )

    together = process(profile, combined)

    assert ledger(together).loc["#3001", "financial_status"] == "paid"
    assert together.summary["net_received"] == D("100.00")
