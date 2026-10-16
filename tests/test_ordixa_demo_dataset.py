"""
tests that the fictional October 2026 demo exports produce the documented results
"""

from decimal import Decimal

import pytest
from openpyxl import load_workbook
from ordixa_golden import DEMO_ISSUES, DEMO_LEDGER, DEMO_TOTALS
from ordixa_helpers import EXPORTS_DIR, build_profile

from app.ordixa.pipeline import process

DEMO_DIR = EXPORTS_DIR / "demo"
# transactions the demo is designed to reject or exclude, keyed by source row
NOT_COUNTED_ROWS = {5, 13, 17, 22, 23}


@pytest.fixture(scope="module")
def demo_result():
    """
    processes the demo exports once
    :returns: run result
    """
    return process(build_profile(), DEMO_DIR)


def test_demo_inputs_cover_csv_and_xlsx():
    """
    tests that the demo includes both supported input formats
    :returns: none
    """
    assert sorted(path.name for path in DEMO_DIR.iterdir()) == [
        "customers.csv",
        "orders_2026-10.csv",
        "payments_2026-10.xlsx",
    ]


def test_demo_payments_workbook_matches_hand_computed_totals():
    """
    tests the raw processor export against the documented totals without
    using the application's parsers
    :returns: none
    """
    sheet = load_workbook(DEMO_DIR / "payments_2026-10.xlsx").active
    by_type = {"Payment": Decimal(0), "Refund": Decimal(0), "Adjustment": Decimal(0)}
    for number, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), 2):
        assert row[6] == "USD"
        if number not in NOT_COUNTED_ROWS:
            by_type[row[3]] += Decimal(repr(row[5]))

    assert by_type["Payment"] == DEMO_TOTALS["payments_received"]
    assert -by_type["Refund"] == DEMO_TOTALS["refunds"]
    assert by_type["Adjustment"] == DEMO_TOTALS["adjustments"]


def test_demo_payments_workbook_holds_no_personal_data():
    """
    tests that the processor export carries no names or email addresses
    :returns: none
    """
    sheet = load_workbook(DEMO_DIR / "payments_2026-10.xlsx").active
    for row in sheet.iter_rows(values_only=True):
        for value in row:
            assert not (isinstance(value, str) and "@" in value)


def test_demo_ledger_matches_hand_computed_results(demo_result):
    """
    tests every reconciled order and the headline totals
    :param demo_result: demo run result
    :returns: none
    """
    ledger = {
        int(row["order_id"]): (
            row["order_total"],
            row["net_paid"],
            row["financial_status"],
            row["outstanding_balance"],
            row["overpayment_amount"],
        )
        for row in demo_result.ledger.to_dict(orient="records")
    }

    assert ledger == DEMO_LEDGER
    for key, value in DEMO_TOTALS.items():
        assert demo_result.summary[key] == value, key
    assert demo_result.summary["status_counts"] == {
        "paid": 9,
        "partial": 3,
        "unpaid": 2,
        "overpaid": 1,
    }


def test_demo_flags_exactly_the_designed_rows(demo_result):
    """
    tests that each seeded problem is reported once with the intended code
    :param demo_result: demo run result
    :returns: none
    """
    issues = {
        (issue.dataset, issue.row): (issue.record_id, issue.code)
        for issue in demo_result.issues
    }

    assert issues == DEMO_ISSUES
    assert demo_result.summary["rejected_rows"] == 8
    assert demo_result.summary["warning_rows"] == 4
    assert demo_result.summary["excluded_rows"] == 1
