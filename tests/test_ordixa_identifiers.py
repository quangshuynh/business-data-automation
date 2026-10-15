"""
tests for text and numeric business identifiers in the Ordixa import path
"""

from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest
from openpyxl import Workbook
from ordixa_golden import TEXT_ID_LEDGER, TEXT_ID_TOTALS
from ordixa_helpers import (
    EXPORTS_DIR,
    TEXT_ID_PROFILE_PATH,
    build_profile,
    csv_to_xlsx,
    issue_codes,
)

from app.ordixa.normalize import (
    NormalizationError,
    identifier_sort_key,
    parse_identifier,
)
from app.ordixa.pipeline import process
from app.ordixa.profile import ProfileError, load_profile

TEXT_IDS = EXPORTS_DIR / "text-ids"


def text(value, prefix=None):
    """
    parses an identifier in text mode
    :param value: raw identifier
    :param prefix: optional profile prefix
    :returns: canonical identifier
    """
    return parse_identifier(value, prefix, mode="text")


def text_error(value, prefix=None):
    """
    returns the error code raised for a text identifier
    :param value: raw identifier
    :param prefix: optional profile prefix
    :returns: error code
    """
    with pytest.raises(NormalizationError) as caught:
        text(value, prefix)
    return caught.value.code


def ledger_view(result):
    """
    reduces a ledger to order -> (total, net, status, outstanding, overpaid)
    :param result: run result
    :returns: dictionary keyed by canonical order id
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


@pytest.fixture(scope="module")
def text_profile():
    """
    loads the text-identifier example profile
    :returns: validated profile
    """
    return load_profile(TEXT_ID_PROFILE_PATH)


# parsing


@pytest.mark.parametrize(
    "value",
    [
        "ORD-2026-00142",
        "INV-A1049",
        "PAY_8F3K2",
        "SQ-2026-10-001",
        "00012345",
        "inv-a1049",
        "#1001",
        "A",
        "0",
        "2026/10/ORD.7:3",
    ],
)
def test_text_identifiers_are_kept_exactly(value):
    """
    letters, case, separators, and leading zeros are preserved
    :param value: identifier as exported
    :returns: none
    """
    assert text(value) == value


def test_text_identifiers_trim_only_surrounding_whitespace():
    """
    surrounding whitespace is export noise; nothing else changes
    :returns: none
    """
    assert text("  ORD-2026-00142\t") == "ORD-2026-00142"
    assert text(" 00012345 ") == "00012345"


def test_text_identifier_prefix_is_removed_exactly():
    """
    a declared prefix is removed literally and must be present
    :returns: none
    """
    assert text("#ORD-7", "#") == "ORD-7"
    assert text("PMT-00042", "PMT-") == "00042"
    assert text_error("ORD-7", "#") == "invalid_identifier"
    assert text_error("#", "#") == "invalid_identifier"


@pytest.mark.parametrize(
    "value",
    [
        "ORD 2026",
        "ORD-2026-00142,",
        "ÖRD-1",
        "-1001",
        ".5",
        "=HYPERLINK(1)",
        "+1001",
        "@SUM",
        "1.0E+12",
        "ORD​1",
        "A" * 65,
    ],
)
def test_text_identifiers_reject_ambiguous_characters(value):
    """
    spaces, signs, commas, non-ASCII, and formula starters are rejected rather
    than silently stripped or folded
    :param value: identifier as exported
    :returns: none
    """
    assert text_error(value) == "invalid_identifier"


def test_text_identifiers_from_numeric_cells():
    """
    whole-number spreadsheet cells become their digits; leading zeros already
    lost by Excel are not reconstructed
    :returns: none
    """
    assert text(12345) == "12345"
    assert text(12345.0) == "12345"
    assert text(Decimal("12345")) == "12345"
    assert text(2**53) == str(2**53)


@pytest.mark.parametrize(
    "value",
    [12.5, float(2**53 + 2), float("inf"), -7, Decimal("1.5"), True],
)
def test_unsafe_numeric_cells_are_rejected(value):
    """
    fractional, negative, boolean, or float values too large to be exact are
    never coerced into identifiers
    :param value: numeric cell value
    :returns: none
    """
    assert text_error(value) == "invalid_identifier"


@pytest.mark.parametrize("value", [date(2026, 10, 1), datetime(2026, 10, 1, 9, 0)])
def test_date_cells_are_not_identifiers(value):
    """
    a date cell in an identifier column is rejected
    :param value: date cell
    :returns: none
    """
    assert text_error(value) == "invalid_identifier"


def test_blank_text_identifier_is_missing():
    """
    blank values keep the missing_identifier code in both modes
    :returns: none
    """
    assert text_error("  ") == "missing_identifier"


def test_numeric_mode_is_unchanged():
    """
    Phase 1A numeric rules still drop leading zeros and reject letters
    :returns: none
    """
    assert parse_identifier("00012345") == 12345
    assert parse_identifier("#1001", "#") == 1001
    assert parse_identifier(1001.0) == 1001
    with pytest.raises(NormalizationError):
        parse_identifier("INV-A1049")


def test_identifiers_sort_naturally():
    """
    ORD-9 sorts before ORD-10, and integers keep numeric order
    :returns: none
    """
    ids = ["ORD-10", "ORD-9", "INV-A1049", "00012", "12", "ORD-010"]

    assert sorted(ids, key=identifier_sort_key) == [
        "00012",
        "12",
        "INV-A1049",
        "ORD-9",
        "ORD-010",
        "ORD-10",
    ]
    assert sorted([10, 9, 100], key=identifier_sort_key) == [9, 10, 100]


# profile


def test_identifier_modes_default_to_numeric():
    """
    Phase 1A profiles without an identifiers table keep numeric identifiers
    :returns: none
    """
    profile = build_profile()

    assert {profile.identifier_mode(name) for name in profile.identifiers} == {
        "numeric"
    }


def test_identifier_modes_are_validated():
    """
    unknown families and modes are reported with the other profile problems
    :returns: none
    """
    with pytest.raises(ProfileError) as caught:
        build_profile(
            lambda d: d.update(identifiers={"order_id": "alpha", "sku_id": "text"})
        )

    problems = "\n".join(caught.value.problems)
    assert "identifiers.order_id: must be one of ['numeric', 'text']" in problems
    assert "identifiers.sku_id: unsupported key" in problems


def test_identifier_mode_applies_to_one_family_only():
    """
    families are configured independently
    :returns: none
    """
    profile = build_profile(lambda d: d.update(identifiers={"payment_id": "text"}))

    assert profile.identifier_mode("payment_id") == "text"
    assert profile.identifier_mode("order_id") == "numeric"


# end to end


def test_text_identifier_fixture_matches_hand_computed_results(text_profile):
    """
    the Juniper Row fixtures reconcile to the values in examples/ordixa/README
    :param text_profile: text-identifier profile
    :returns: none
    """
    result = process(text_profile, TEXT_IDS)

    assert ledger_view(result) == TEXT_ID_LEDGER
    for key, expected in TEXT_ID_TOTALS.items():
        assert result.summary[key] == expected, key
    assert list(result.ledger["order_id"]) == sorted(TEXT_ID_LEDGER)


def test_text_identifiers_keep_leading_zeros_through_the_join(text_profile):
    """
    customer 00012345 joins as text; a nameless customer is still on file
    :param text_profile: text-identifier profile
    :returns: none
    """
    result = process(text_profile, TEXT_IDS)
    rows = result.ledger.set_index("order_id")

    assert rows.loc["ORD-2026-00142", "customer_id"] == "00012345"
    assert rows.loc["ORD-2026-00142", "customer_name"] == "Morgan Vale"
    assert rows.loc["ORD-2026-00143", "customer_found"]
    assert pd.isna(rows.loc["ORD-2026-00143", "customer_name"])
    assert pd.isna(rows.loc["ORD-2026-00009", "customer_id"])
    assert issue_codes(result, "00012346") == ["missing_name", "missing_phone"]
    assert issue_codes(result, "ORD-2026-00009") == ["missing_customer_reference"]


def test_text_identifiers_csv_and_xlsx_agree(text_profile, tmp_path):
    """
    the same exports saved as XLSX text cells reconcile identically
    :param text_profile: text-identifier profile
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    for path in TEXT_IDS.glob("*.csv"):
        csv_to_xlsx(path, tmp_path / f"{path.stem}.xlsx")

    from_csv = process(text_profile, TEXT_IDS)
    from_xlsx = process(text_profile, tmp_path)

    assert ledger_view(from_xlsx) == ledger_view(from_csv)
    assert from_xlsx.summary == from_csv.summary


def test_excel_numeric_cells_do_not_recover_lost_leading_zeros(text_profile, tmp_path):
    """
    if Excel already turned 00012345 into the number 12345, the customer no
    longer matches the order's 00012345 and the mismatch is reported
    :param text_profile: text-identifier profile
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    for name in ("orders_2026-10.csv", "payments_2026-10.csv"):
        csv_to_xlsx(TEXT_IDS / name, tmp_path / name.replace(".csv", ".xlsx"))
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Customer Number", "Full Name", "Email", "Phone"])
    sheet.append([12345, "Morgan Vale", "morgan.vale@example.com", "555-010-0201"])
    workbook.save(tmp_path / "customers.xlsx")

    result = process(text_profile, tmp_path)
    rows = result.ledger.set_index("order_id")

    assert not rows.loc["ORD-2026-00142", "customer_found"]
    assert issue_codes(result, "ORD-2026-00142") == ["customer_not_found"]
    assert result.summary["net_received"] == TEXT_ID_TOTALS["net_received"]
