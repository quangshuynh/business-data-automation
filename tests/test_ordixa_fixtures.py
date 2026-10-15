import csv
import re
from decimal import Decimal
from pathlib import Path

import pytest
from ordixa_golden import CLEAN_LEDGER, CLEAN_TOTALS

EXPORTS_DIR = Path(__file__).resolve().parents[1] / "examples" / "ordixa" / "exports"
RESERVED_DOMAINS = {"example.com", "example.net", "example.org"}
EMAIL_LIKE = re.compile(r"[^\s,@]+@([^\s,]*)")


def read_rows(path):
    """
    reads a fixture CSV into dictionaries
    :param path: fixture file path
    :returns: list of row dictionaries
    """
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def plain_amount(text):
    """
    converts a fixture amount to a decimal with deliberately minimal parsing
    :param text: amount text such as -$1,999.99
    :returns: decimal amount
    """
    return Decimal(text.replace("$", "").replace(",", ""))


@pytest.mark.parametrize("fixture_set", ["clean", "problematic"])
def test_fixtures_only_use_reserved_example_domains(fixture_set):
    """
    tests that fixture email addresses never use a real domain
    :param fixture_set: fixture directory name
    :returns: none
    """
    for path in (EXPORTS_DIR / fixture_set).glob("*.csv"):
        for domain in EMAIL_LIKE.findall(path.read_text(encoding="utf-8")):
            assert domain in RESERVED_DOMAINS | {""}, f"{path.name}: {domain}"


@pytest.mark.parametrize("fixture_set", ["clean", "problematic"])
def test_fixture_phone_numbers_use_fictional_range(fixture_set):
    """
    tests that North American fixture phone numbers use the 555-01xx range
    :param fixture_set: fixture directory name
    :returns: none
    """
    for row in read_rows(EXPORTS_DIR / fixture_set / "customers.csv"):
        digits = re.sub(r"\D", "", row["Phone"])
        if len(digits) == 10:
            assert digits[3:6] == "010", row["Phone"]


def test_clean_fixture_matches_hand_computed_totals():
    """
    tests that the clean fixture files agree with the documented expectations
    :returns: none
    """
    clean = EXPORTS_DIR / "clean"
    orders = [
        row for path in sorted(clean.glob("orders_*.csv")) for row in read_rows(path)
    ]
    payments = [
        row for path in sorted(clean.glob("payments_*.csv")) for row in read_rows(path)
    ]

    order_totals = {int(row["Name"][1:]): plain_amount(row["Total"]) for row in orders}
    assert order_totals == {key: value[0] for key, value in CLEAN_LEDGER.items()}
    assert sum(order_totals.values()) == CLEAN_TOTALS["order_value"]

    by_type = {"Payment": Decimal(0), "Refund": Decimal(0), "Adjustment": Decimal(0)}
    for row in payments:
        by_type[row["Type"]] += plain_amount(row["Amount"])

    assert by_type["Payment"] == CLEAN_TOTALS["gross_payments"]
    assert -by_type["Refund"] == CLEAN_TOTALS["refunds"]
    assert by_type["Adjustment"] == CLEAN_TOTALS["adjustments"]
    assert sum(by_type.values()) == CLEAN_TOTALS["net_received"]
