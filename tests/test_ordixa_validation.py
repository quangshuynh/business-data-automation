import shutil
from decimal import Decimal

import pandas as pd
import pytest
from ordixa_golden import (
    CLEAN_LEDGER,
    CLEAN_TOTALS,
    PROBLEMATIC_COUNTS,
    PROBLEMATIC_LEDGER,
    PROBLEMATIC_TOTALS,
)
from ordixa_helpers import EXPORTS_DIR, build_profile, copy_exports

from app.ordixa import pipeline
from app.ordixa.pipeline import ReconciliationIntegrityError, process
from app.reconciliation.reconcile import build_report


def ledger_view(result):
    """
    reduces a ledger to the values recorded in the golden expectations
    :param result: run result
    :returns: mapping of order id to golden tuple
    """
    return {
        row["order_id"]: (
            row["order_total"],
            row["net_paid"],
            row["financial_status"],
            row["outstanding_balance"],
            row["overpayment_amount"],
        )
        for row in result.ledger.to_dict(orient="records")
    }


def issues_for(result, record_id):
    """
    lists issue codes for one source reference
    :param result: run result
    :param record_id: source reference such as #2003
    :returns: list of codes
    """
    return [issue.code for issue in result.issues if issue.record_id == record_id]


@pytest.fixture(scope="module")
def clean_result():
    """
    processes the clean fixture set once
    :returns: run result
    """
    return process(build_profile(), EXPORTS_DIR / "clean")


@pytest.fixture(scope="module")
def problematic_result():
    """
    processes the problematic fixture set once
    :returns: run result
    """
    return process(build_profile(), EXPORTS_DIR / "problematic")


def test_clean_fixture_matches_hand_computed_ledger(clean_result):
    """
    tests every reconciled order against independently computed values
    :param clean_result: run result for the clean fixtures
    :returns: none
    """
    assert ledger_view(clean_result) == CLEAN_LEDGER
    assert clean_result.issues == []


def test_clean_fixture_matches_hand_computed_totals(clean_result):
    """
    tests run totals against independently computed values
    :param clean_result: run result for the clean fixtures
    :returns: none
    """
    summary = clean_result.summary

    assert summary["order_value"] == CLEAN_TOTALS["order_value"]
    assert summary["payments_received"] == CLEAN_TOTALS["gross_payments"]
    assert summary["refunds"] == CLEAN_TOTALS["refunds"]
    assert summary["adjustments"] == CLEAN_TOTALS["adjustments"]
    assert summary["net_received"] == CLEAN_TOTALS["net_received"]
    assert summary["outstanding_balance"] == CLEAN_TOTALS["outstanding"]
    assert summary["overpayments"] == CLEAN_TOTALS["overpaid"]
    assert summary["applied_to_orders"] == CLEAN_TOTALS["applied"]
    assert summary["status_counts"] == {
        "paid": 3,
        "partial": 2,
        "unpaid": 3,
        "overpaid": 1,
    }
    assert all(isinstance(value, Decimal) for value in CLEAN_TOTALS.values())


def test_problematic_fixture_matches_hand_computed_results(problematic_result):
    """
    tests the defect fixture against independently computed outcomes
    :param problematic_result: run result for the problematic fixtures
    :returns: none
    """
    summary = problematic_result.summary

    assert ledger_view(problematic_result) == PROBLEMATIC_LEDGER
    assert summary["order_value"] == PROBLEMATIC_TOTALS["order_value"]
    assert summary["net_received"] == PROBLEMATIC_TOTALS["net_received"]
    assert summary["outstanding_balance"] == PROBLEMATIC_TOTALS["outstanding"]
    assert summary["overpayments"] == PROBLEMATIC_TOTALS["overpaid"]
    for dataset, expected in PROBLEMATIC_COUNTS.items():
        counts = problematic_result.counts[dataset]
        assert {key: counts[key] for key in expected} == expected, dataset


def test_contact_warnings_do_not_cascade_to_orders_or_payments(problematic_result):
    """
    regression: an invalid customer email used to quarantine the customer and,
    through it, every related order and payment
    :param problematic_result: run result for the problematic fixtures
    :returns: none
    """
    ledger = problematic_result.ledger.set_index("order_ref")

    assert issues_for(problematic_result, "7000102") == ["invalid_email"]
    assert issues_for(problematic_result, "#2002") == []
    assert ledger.loc["#2002", "customer_found"]
    assert ledger.loc["#2002", "net_paid"] == Decimal("175.00")
    assert ledger.loc["#2002", "financial_status"] == "partial"


def test_missing_customer_is_a_warning_by_default(problematic_result):
    """
    tests that unknown or unreadable customer references keep the order
    :param problematic_result: run result for the problematic fixtures
    :returns: none
    """
    ledger = problematic_result.ledger.set_index("order_ref")

    assert issues_for(problematic_result, "#2003") == ["customer_not_found"]
    assert issues_for(problematic_result, "#2011") == ["invalid_identifier"]
    assert not ledger.loc["#2003", "customer_found"]
    assert ledger.loc["#2003", "financial_status"] == "paid"


def test_missing_customer_can_be_made_blocking():
    """
    tests the strict profile setting and its cascade to payments
    :returns: none
    """
    profile = build_profile(
        lambda d: d["reconciliation"].update(missing_customer="error")
    )

    result = process(profile, EXPORTS_DIR / "problematic")

    assert set(PROBLEMATIC_LEDGER) - set(result.ledger["order_id"]) == {2003, 2011}
    assert issues_for(result, "PMT-270003") == ["order_rejected"]
    assert issues_for(result, "PMT-270016") == ["order_rejected"]


def test_guest_order_without_customer_reference_is_reconciled(tmp_path):
    """
    tests that a blank customer reference produces a warning, not a rejection
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = copy_exports("clean", tmp_path / "in")
    path = input_dir / "orders_2026-09.csv"
    path.write_text(
        path.read_text("utf-8").replace(
            "#1009,2026-09-28 19:45:00 -0400,7000104",
            ("#1009,2026-09-28 19:45:00 -0400,"),
        ),
        encoding="utf-8",
    )

    result = process(build_profile(), input_dir)
    ledger = result.ledger.set_index("order_ref")

    assert issues_for(result, "#1009") == ["missing_customer_reference"]
    assert pd.isna(ledger.loc["#1009", "customer_id"])
    assert ledger.loc["#1006", "customer_id"] == 7000101
    assert ledger.loc["#1009", "outstanding_balance"] == Decimal("45.00")


def test_exact_duplicate_transactions_are_counted_once(problematic_result):
    """
    tests that a repeated transaction row cannot inflate totals
    :param problematic_result: run result for the problematic fixtures
    :returns: none
    """
    ledger = problematic_result.ledger.set_index("order_ref")

    assert issues_for(problematic_result, "PMT-270005") == ["duplicate_row"]
    assert ledger.loc["#2007", "net_paid"] == Decimal("60.00")
    assert ledger.loc["#2007", "transaction_count"] == 1


def test_conflicting_duplicates_are_rejected_entirely(problematic_result):
    """
    tests that identifiers with contradictory rows are not guessed
    :param problematic_result: run result for the problematic fixtures
    :returns: none
    """
    assert issues_for(problematic_result, "#2008") == [
        "conflicting_duplicate_id",
        "conflicting_duplicate_id",
    ]
    assert 2008 not in set(problematic_result.ledger["order_id"])
    assert issues_for(problematic_result, "PMT-270013") == [
        "conflicting_duplicate_id",
        "conflicting_duplicate_id",
    ]
    assert problematic_result.ledger.set_index("order_ref").loc[
        "#2010", "net_paid"
    ] == Decimal("1350.00")


def test_overlapping_export_files_do_not_double_count(tmp_path, clean_result):
    """
    tests that the same transactions exported twice yield identical results
    :param tmp_path: pytest temporary directory
    :param clean_result: run result for the clean fixtures
    :returns: none
    """
    input_dir = copy_exports("clean", tmp_path / "in")
    shutil.copy(
        input_dir / "payments_2026-08.csv", input_dir / "payments_2026-08_resend.csv"
    )

    result = process(build_profile(), input_dir)

    assert ledger_view(result) == CLEAN_LEDGER
    assert result.summary["net_received"] == clean_result.summary["net_received"]
    assert result.counts["payments"]["rejected"] == 5
    assert {issue.code for issue in result.issues} == {"duplicate_row"}


def test_payments_for_orders_outside_the_run_are_rejected(tmp_path):
    """
    tests the documented limitation: no matching against earlier imports
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = copy_exports(
        "clean",
        tmp_path / "in",
        {"customers.csv", "orders_2026-09.csv", "payments_2026-09.csv"},
    )

    result = process(build_profile(), input_dir)

    assert issues_for(result, "PMT-260901") == ["order_not_in_run"]
    assert "same run" in result.issues[0].message
    assert 1002 not in set(result.ledger["order_id"])


def test_processing_both_periods_together_reconciles_installments(tmp_path):
    """
    tests that an August order paid in two periods is complete when both
    periods are processed in one run, and incomplete for August alone
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    august = copy_exports(
        "clean",
        tmp_path / "aug",
        {"customers.csv", "orders_2026-08.csv", "payments_2026-08.csv"},
    )

    august_result = process(build_profile(), august)
    both_result = process(build_profile(), EXPORTS_DIR / "clean")

    def net_paid(result):
        return result.ledger.set_index("order_ref").loc["#1002", "net_paid"]

    assert net_paid(august_result) == Decimal("500.00")
    assert net_paid(both_result) == Decimal("1000.00")


def test_unmapped_status_and_bad_refund_sign_are_blocking(problematic_result):
    """
    tests that unknown statuses and refund sign violations reject the row
    :param problematic_result: run result for the problematic fixtures
    :returns: none
    """
    assert issues_for(problematic_result, "PMT-270006") == ["unmapped_status"]
    assert issues_for(problematic_result, "PMT-270009") == ["refund_sign"]
    assert issues_for(problematic_result, "PMT-270010") == ["excluded_status"]
    assert issues_for(problematic_result, "PMT-270017") == [
        "invalid_transaction_amount"
    ]


def test_repeated_processing_is_deterministic(clean_result):
    """
    tests that the same inputs give identical business results
    :param clean_result: run result for the clean fixtures
    :returns: none
    """
    again = process(build_profile(), EXPORTS_DIR / "clean")

    pd.testing.assert_frame_equal(again.ledger, clean_result.ledger)
    assert again.summary == clean_result.summary


def test_integrity_check_detects_double_counting(monkeypatch):
    """
    tests that the independent cross-check stops a run with inflated totals
    :param monkeypatch: pytest fixture for replacing the engine
    :returns: none
    """

    def doubled_report(customers, orders, payments):
        return build_report(customers, orders, pd.concat([payments, payments.head(1)]))

    monkeypatch.setattr(pipeline, "build_report", doubled_report)
    monkeypatch.setattr(
        "app.reconciliation.reconcile.ensure_unique_ids", lambda *args: None
    )

    with pytest.raises(ReconciliationIntegrityError, match="net paid"):
        process(build_profile(), EXPORTS_DIR / "clean")


@pytest.mark.parametrize(
    ("dataset", "column"),
    [("payments", "payment_id"), ("orders", "order_id"), ("customers", "customer_id")],
)
def test_engine_refuses_duplicate_identifiers(dataset, column):
    """
    tests the engine-level guard against counting a record twice
    :param dataset: dataset receiving a duplicate
    :param column: identifier column
    :returns: none
    """
    frames = {
        "customers": pd.DataFrame([{"customer_id": 1001, "name": "Avery Quinn"}]),
        "orders": pd.DataFrame([{"order_id": 5001, "customer_id": 1001, "total": 10}]),
        "payments": pd.DataFrame(
            [
                {
                    "payment_id": 9001,
                    "order_id": 5001,
                    "amount": 10,
                    "transaction_type": "payment",
                    "status": "paid",
                }
            ]
        ),
    }
    frames[dataset] = pd.concat([frames[dataset], frames[dataset]])

    with pytest.raises(ValueError, match=f"duplicate {column}.*more than once"):
        build_report(frames["customers"], frames["orders"], frames["payments"])


def test_engine_reports_customer_found_for_customer_without_name():
    """
    tests that customer matching no longer depends on the optional name field
    :returns: none
    """
    customers = pd.DataFrame([{"customer_id": 1001, "name": None}])
    orders = pd.DataFrame(
        [
            {"order_id": 5001, "customer_id": 1001, "total": 10},
            {"order_id": 5002, "customer_id": 1002, "total": 10},
        ]
    )
    payments = pd.DataFrame(
        columns=["payment_id", "order_id", "amount", "transaction_type", "status"]
    )

    report = build_report(customers, orders, payments).set_index("order_id")

    assert bool(report.loc[5001, "customer_found"]) is True
    assert bool(report.loc[5002, "customer_found"]) is False
