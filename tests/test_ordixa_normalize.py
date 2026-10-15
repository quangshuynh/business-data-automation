from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.ordixa.normalize import (
    NormalizationError,
    parse_amount,
    parse_currency,
    parse_date,
    parse_identifier,
)
from app.ordixa.profile import AmountRules

US_RULES = AmountRules(
    currency="USD",
    currency_symbols=("$",),
    thousands_separator=",",
    decimal_separator=".",
    negative_styles=frozenset({"minus", "parentheses"}),
)
EU_RULES = AmountRules(
    currency="EUR",
    currency_symbols=("€",),
    thousands_separator=".",
    decimal_separator=",",
)


def error_code(function, *args):
    """
    runs a normalizer that should fail
    :param function: normalization function
    :param args: arguments for the function
    :returns: the normalization error code
    """
    with pytest.raises(NormalizationError) as error:
        function(*args)
    return error.value.code


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("129.99", "129.99"),
        ("$129.99", "129.99"),
        ("$1,999.99", "1999.99"),
        ("1,234,567.80", "1234567.80"),
        ("-$89.00", "-89.00"),
        ("$-89.00", "-89.00"),
        ("($3.00)", "-3.00"),
        ("  42 ", "42.00"),
        ("7.5", "7.50"),
        ("12$", "12.00"),
    ],
)
def test_us_amounts_parse_exactly(text, expected):
    """
    tests that declared US conventions parse into exact decimals
    :param text: source amount text
    :param expected: expected decimal string
    :returns: none
    """
    amount = parse_amount(text, US_RULES)

    assert isinstance(amount, Decimal)
    assert amount == Decimal(expected)
    assert str(amount) == expected


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("1.234,56", "invalid_amount"),
        ("12,34", "invalid_amount"),
        ("1,2345.00", "invalid_amount"),
        ("12.345", "too_many_decimal_places"),
        ("abc", "invalid_amount"),
        ("€12.00", "invalid_amount"),
        ("--5.00", "invalid_amount"),
        ("-($5.00)", "invalid_amount"),
        ("1e3", "invalid_amount"),
        ("NaN", "invalid_amount"),
        ("10000000000.00", "amount_out_of_range"),
        ("", "missing_amount"),
    ],
)
def test_ambiguous_or_invalid_us_amounts_are_rejected(text, code):
    """
    tests that amounts outside the declared conventions are rejected
    :param text: source amount text
    :param code: expected error code
    :returns: none
    """
    assert error_code(parse_amount, text, US_RULES) == code


def test_regional_separators_follow_the_profile():
    """
    tests that European separators parse only under a European profile
    :returns: none
    """
    assert parse_amount("1.234,56 €", EU_RULES) == Decimal("1234.56")
    assert parse_amount("€ 0,50", EU_RULES) == Decimal("0.50")
    assert error_code(parse_amount, "1,234.56", EU_RULES) == "invalid_amount"
    assert error_code(parse_amount, "(5,00)", EU_RULES) == "invalid_amount"


def test_native_spreadsheet_numbers_keep_their_displayed_value():
    """
    tests that typed numeric cells are converted without float drift
    :returns: none
    """
    assert parse_amount(129.99, US_RULES) == Decimal("129.99")
    assert error_code(parse_amount, 0.1 + 0.2, US_RULES) == "too_many_decimal_places"
    assert parse_amount(1250, US_RULES) == Decimal("1250.00")
    assert error_code(parse_amount, True, US_RULES) == "invalid_amount"


@pytest.mark.parametrize(
    ("value", "prefix", "expected"),
    [
        ("#1001", "#", 1001),
        ("PMT-260801", "PMT-", 260801),
        ("7000101", None, 7000101),
        (7000101, None, 7000101),
        (7000101.0, None, 7000101),
    ],
)
def test_identifiers_normalize(value, prefix, expected):
    """
    tests identifier prefix handling
    :param value: raw identifier
    :param prefix: declared prefix
    :param expected: canonical identifier
    :returns: none
    """
    assert parse_identifier(value, prefix) == expected


@pytest.mark.parametrize(
    ("value", "prefix", "code"),
    [
        ("1001", "#", "invalid_identifier"),
        ("#10.01", "#", "invalid_identifier"),
        ("#-5", "#", "invalid_identifier"),
        ("#0", "#", "invalid_identifier"),
        ("ABC-17", None, "invalid_identifier"),
        ("1001.5", None, "invalid_identifier"),
        ("", "#", "missing_identifier"),
        (None, None, "missing_identifier"),
    ],
)
def test_invalid_identifiers_are_rejected(value, prefix, code):
    """
    tests identifier rejection codes
    :param value: raw identifier
    :param prefix: declared prefix
    :param code: expected error code
    :returns: none
    """
    assert error_code(parse_identifier, value, prefix) == code


def test_dates_use_declared_formats_only():
    """
    tests explicit date formats, including a time zone offset kept as written
    :returns: none
    """
    formats = ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d")

    assert parse_date("2026-08-03 23:30:00 -0400", formats) == date(2026, 8, 3)
    assert parse_date("2026-08-03", formats) == date(2026, 8, 3)
    assert error_code(parse_date, "08/03/2026", formats) == "invalid_date"
    assert error_code(parse_date, "Aug 3 2026", formats) == "invalid_date"


def test_timestamps_are_not_shifted_across_time_zones():
    """
    tests that a late-evening local timestamp keeps its local calendar date
    :returns: none
    """
    # 23:30 at -04:00 is already the next day in UTC; the source date is kept
    assert parse_date("2026-08-31 23:30:00 -0400", ("%Y-%m-%d %H:%M:%S %z",)) == date(
        2026, 8, 31
    )
    aware = datetime(2026, 8, 31, 23, 30, tzinfo=timezone(timedelta(hours=-4)))
    assert parse_date(aware, ()) == date(2026, 8, 31)


@pytest.mark.parametrize(
    ("text", "formats", "expected"),
    [
        ("03/04/2026", ("%m/%d/%Y",), date(2026, 3, 4)),
        ("03/04/2026", ("%d/%m/%Y",), date(2026, 4, 3)),
        ("13/04/2026", ("%m/%d/%Y", "%d/%m/%Y"), date(2026, 4, 13)),
        ("04/04/2026", ("%m/%d/%Y", "%d/%m/%Y"), date(2026, 4, 4)),
        ("03.04.2026", ("%d.%m.%Y",), date(2026, 4, 3)),
    ],
)
def test_regional_date_conventions(text, formats, expected):
    """
    tests US and European day-month ordering when declared
    :param text: source date
    :param formats: declared formats
    :param expected: expected calendar date
    :returns: none
    """
    assert parse_date(text, formats) == expected


def test_ambiguous_dates_are_rejected_with_both_readings():
    """
    tests that a date readable two ways under the declared formats is rejected
    :returns: none
    """
    with pytest.raises(NormalizationError) as error:
        parse_date("03/04/2026", ("%m/%d/%Y", "%d/%m/%Y"))

    assert error.value.code == "ambiguous_date"
    assert "2026-03-04" in str(error.value)
    assert "2026-04-03" in str(error.value)


@pytest.mark.parametrize("text", ["02/30/2026", "02/29/2025", "04/31/2026"])
def test_invalid_calendar_dates_are_explained(text):
    """
    tests that impossible dates are distinguished from format mismatches
    :param text: impossible date
    :returns: none
    """
    assert error_code(parse_date, text, ("%m/%d/%Y",)) == "invalid_calendar_date"


def test_leap_day_is_accepted():
    """
    tests a valid leap day
    :returns: none
    """
    assert parse_date("02/29/2028", ("%m/%d/%Y",)) == date(2028, 2, 29)


def test_currency_is_never_converted():
    """
    tests currency code validation
    :returns: none
    """
    assert parse_currency(" usd ", "USD") == "USD"
    assert error_code(parse_currency, "EUR", "USD") == "currency_mismatch"
    assert error_code(parse_currency, "", "USD") == "missing_currency"
