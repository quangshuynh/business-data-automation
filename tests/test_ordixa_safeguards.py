"""
tests for identifier collision, case-variant, and duplicate safeguards
"""

from decimal import Decimal

import pytest
from openpyxl import Workbook
from ordixa_helpers import (
    ORDER_HEADER,
    PAYMENT_HEADER,
    build_profile,
    issue_codes,
    write_exports,
    write_rows,
)

from app.ordixa.pipeline import process

D = Decimal
TEXT_MODES = {"customer_id": "text", "order_id": "text", "payment_id": "text"}


def text_profile():
    """
    builds the Harbor Lane profile with text identifiers in every family
    :returns: validated profile
    """
    return build_profile(lambda d: d.update(identifiers=dict(TEXT_MODES)))


def order(ref, total="10.00"):
    """
    builds an order row
    :param ref: order name
    :param total: order total
    :returns: list of cells
    """
    return [ref, "2026-08-01", "7000101", "USD", total]


def payment(ref, order_ref, amount="$10.00"):
    """
    builds a paid payment row
    :param ref: transaction id
    :param order_ref: order reference
    :param amount: amount text
    :returns: list of cells
    """
    return [ref, order_ref, "08/02/2026", "Payment", "Paid", amount, "USD"]


def messages(result, code):
    """
    collects the messages recorded for one issue code
    :param result: run result
    :param code: issue code
    :returns: list of messages
    """
    return [issue.message for issue in result.issues if issue.code == code]


def test_numeric_spellings_that_collide_are_quarantined(tmp_path):
    """
    regression: #1001 and #01001 both normalize to 1001; identical content used
    to be merged silently as an exact duplicate
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = write_exports(
        tmp_path / "in",
        orders=[order("#1001"), order("#01001")],
        payments=[payment("PMT-1", "#1001")],
    )

    result = process(build_profile(), input_dir)

    assert issue_codes(result, "#1001") == ["identifier_collision"]
    assert issue_codes(result, "#01001") == ["identifier_collision"]
    assert "'#01001', '#1001'" in messages(result, "identifier_collision")[0]
    assert issue_codes(result, "PMT-1") == ["order_rejected"]
    assert result.ledger.empty
    assert result.summary["net_received"] == D("0.00")


def test_colliding_transaction_ids_across_files_are_not_counted(tmp_path):
    """
    PMT-0007 in one file and PMT-7 in another cannot both count, and neither
    is silently chosen
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = write_exports(
        tmp_path / "in",
        orders=[order("#1001", "20.00")],
        payments=[payment("PMT-0007", "#1001")],
    )
    write_rows(
        input_dir / "payments_2.csv", PAYMENT_HEADER, [payment("PMT-7", "#1001")]
    )

    result = process(build_profile(), input_dir)

    assert issue_codes(result, "PMT-0007") == ["identifier_collision"]
    assert issue_codes(result, "PMT-7") == ["identifier_collision"]
    assert result.ledger.set_index("order_ref").loc["#1001", "net_paid"] == D("0.00")


def test_numeric_cells_and_text_with_same_digits_do_not_collide(tmp_path):
    """
    the XLSX number 7000101 and CSV text 7000101 are the same spelling
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = write_exports(
        tmp_path / "in",
        orders=[order("#1001")],
        payments=[payment("PMT-1", "#1001")],
        customers=[["7000101", "Avery", "Quinn", "a@example.com", "555-010-0101"]],
    )
    workbook = Workbook()
    workbook.active.append(["Customer ID", "First Name", "Last Name", "Email", "Phone"])
    workbook.active.append([7000101, "Avery", "Quinn", "a@example.com", "555-010-0101"])
    workbook.save(input_dir / "customers_copy.xlsx")

    result = process(build_profile(), input_dir)

    assert issue_codes(result, "7000101") == ["duplicate_row"]
    assert result.ledger.set_index("order_ref").loc["#1001", "customer_found"]


def test_text_identifiers_with_leading_zeros_are_distinct(tmp_path):
    """
    in text mode 00012 and 12 are different orders, never a collision
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = write_exports(
        tmp_path / "in",
        orders=[order("#00012", "10.00"), order("#12", "20.00")],
        payments=[payment("PMT-A", "#00012"), payment("PMT-B", "#12", "$20.00")],
    )

    result = process(text_profile(), input_dir)
    rows = result.ledger.set_index("order_id")

    assert result.issues == []
    assert rows.loc["00012", "financial_status"] == "paid"
    assert rows.loc["12", "net_paid"] == D("20.00")


def test_text_identifier_whitespace_variants_are_one_record(tmp_path):
    """
    surrounding whitespace is not part of the identifier, so a padded copy of
    an identical row is an exact duplicate counted once
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = write_exports(
        tmp_path / "in",
        orders=[order("#ORD-1")],
        payments=[payment("PMT-A", "#ORD-1"), payment(" PMT-A ", "#ORD-1")],
    )

    result = process(text_profile(), input_dir)

    assert result.summary["net_received"] == D("10.00")
    assert issue_codes(result, "PMT-A") == ["duplicate_row"]


def test_text_identifiers_differing_only_by_case_are_flagged(tmp_path):
    """
    INV-A1049 and inv-a1049 stay separate (no case folding) but are both
    flagged, and a payment that matches neither exactly gets a hint
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = write_exports(
        tmp_path / "in",
        orders=[order("#INV-A1049", "10.00"), order("#inv-a1049", "30.00")],
        payments=[
            payment("PMT-A", "#INV-A1049"),
            payment("PMT-B", "#Inv-A1049", "$30.00"),
        ],
    )

    result = process(text_profile(), input_dir)
    rows = result.ledger.set_index("order_id")

    assert issue_codes(result, "#INV-A1049") == ["identifier_case_variant"]
    assert issue_codes(result, "#inv-a1049") == ["identifier_case_variant"]
    assert rows.loc["INV-A1049", "financial_status"] == "paid"
    assert rows.loc["inv-a1049", "financial_status"] == "unpaid"
    assert issue_codes(result, "PMT-B") == ["order_not_in_run"]
    assert "differs only in letter case" in messages(result, "order_not_in_run")[0]


@pytest.mark.parametrize("mode", ["numeric", "text"])
def test_same_order_in_two_period_files_still_counts_once(tmp_path, mode):
    """
    collision checks do not disturb the exact-duplicate rule in either mode
    :param tmp_path: pytest temporary directory
    :param mode: identifier mode
    :returns: none
    """
    input_dir = write_exports(
        tmp_path / "in",
        orders=[order("#1001", "40.00")],
        payments=[payment("PMT-1", "#1001", "$40.00")],
    )
    write_rows(input_dir / "orders_09.csv", ORDER_HEADER, [order("#1001", "40.00")])
    profile = text_profile() if mode == "text" else build_profile()

    result = process(profile, input_dir)

    assert issue_codes(result, "#1001") == ["duplicate_row"]
    assert result.summary["order_value"] == D("40.00")
    assert result.summary["net_received"] == D("40.00")
