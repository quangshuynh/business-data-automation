import math
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.validators.validate import CENT, MAX_FINANCIAL_AMOUNT, normalize_id

DIGITS_PATTERN = re.compile(r"^[0-9]+$")
# text identifiers: ASCII letters and digits plus the separators vendors use;
# the first character must be a letter, digit, or # so a value can never read
# as a signed number or a spreadsheet formula
TEXT_ID_PATTERN = re.compile(r"^[A-Za-z0-9#][A-Za-z0-9#._/:-]*$")
TEXT_ID_CHARACTERS = "letters, digits, and the separators - _ . / : #"
MAX_TEXT_ID_LENGTH = 64
# larger binary floats cannot represent every whole number exactly
MAX_EXACT_FLOAT_ID = 2**53
NATURAL_CHUNKS = re.compile(r"([0-9]+)")


class NormalizationError(ValueError):
    """error raised when a source value cannot be normalized safely"""

    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def is_blank(value):
    """
    checks whether a source cell is empty
    :param value: raw source value
    :returns: true for none, nan, and whitespace-only strings
    """
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and not value.strip()


def display_value(value):
    """
    converts a raw source value into text for explanations
    :param value: raw source value
    :returns: text representation, empty for blank values
    """
    if is_blank(value):
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def identifier_spelling(value):
    """
    gives the identifier exactly as the export spelled it, ignoring only
    surrounding whitespace and the float form of a whole-number spreadsheet cell
    :param value: raw identifier value
    :returns: identifier text
    """
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return display_value(value)


def strip_prefix(text, prefix):
    """
    removes a profile-declared literal prefix
    :param text: identifier text
    :param prefix: prefix declared by the profile, or none
    :returns: text after the prefix
    """
    if not prefix:
        return text
    if not text.startswith(prefix):
        raise NormalizationError(
            "invalid_identifier",
            f"{text!r} does not start with the expected prefix {prefix!r}",
        )
    return text[len(prefix) :]


def numeric_cell_text(value):
    """
    converts a numeric spreadsheet cell into identifier text without passing a
    large or fractional value through binary floating point
    :param value: int, float, or decimal cell value
    :returns: whole-number text
    """
    text = display_value(value)
    if isinstance(value, float):
        exact = math.isfinite(value) and value.is_integer()
        if not exact or abs(value) > MAX_EXACT_FLOAT_ID:
            raise NormalizationError(
                "invalid_identifier",
                f"{text!r} is a numeric cell that cannot be an exact identifier; "
                "format the identifier column as Text in the source workbook",
            )
        value = int(value)
    elif isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            raise NormalizationError(
                "invalid_identifier", f"{text!r} is not a whole-number identifier"
            )
        value = int(value)

    if value < 0:
        raise NormalizationError(
            "invalid_identifier", f"{text!r} is a negative number, not an identifier"
        )
    return str(value)


def parse_text_identifier(value, prefix=None):
    """
    normalizes an identifier as opaque text such as ORD-2026-00142 or 00012345

    only surrounding whitespace and the declared prefix are removed; letters keep
    their case and leading zeros are kept, so two different spellings never
    become the same identifier
    :param value: raw identifier value
    :param prefix: optional literal prefix declared by the profile
    :returns: identifier text
    """
    if isinstance(value, (datetime, date)):
        raise NormalizationError(
            "invalid_identifier",
            f"{display_value(value)!r} is a date cell, not an identifier",
        )

    if isinstance(value, (int, float, Decimal)):
        text = numeric_cell_text(value)
    else:
        text = display_value(value)
    original = text
    text = strip_prefix(text, prefix)

    if not text:
        raise NormalizationError(
            "invalid_identifier", f"{original!r} has nothing after the prefix"
        )
    if len(text) > MAX_TEXT_ID_LENGTH:
        raise NormalizationError(
            "invalid_identifier",
            f"identifier is longer than {MAX_TEXT_ID_LENGTH} characters",
        )
    if not TEXT_ID_PATTERN.match(text):
        raise NormalizationError(
            "invalid_identifier",
            f"{original!r} is not a valid identifier (expected "
            f"{TEXT_ID_CHARACTERS}, starting with a letter, digit, or #; "
            "spaces are not allowed)",
        )

    return text


def parse_identifier(value, prefix=None, mode="numeric"):
    """
    normalizes a business identifier into its canonical form
    :param value: raw identifier such as #1001, PMT-260801, or ORD-2026-00142
    :param prefix: optional literal prefix declared by the profile
    :param mode: numeric (positive integer, Phase 1A) or text (exact string)
    :returns: positive integer in numeric mode, text in text mode
    """
    if is_blank(value):
        raise NormalizationError("missing_identifier", "identifier is blank")

    if isinstance(value, bool):
        raise NormalizationError("invalid_identifier", "identifier is not a number")

    if mode == "text":
        return parse_text_identifier(value, prefix)

    if isinstance(value, (int, float)) and not prefix:
        identifier = normalize_id(value)
        if identifier is None:
            raise NormalizationError(
                "invalid_identifier",
                f"{display_value(value)!r} is not a positive whole-number identifier",
            )
        return identifier

    text = display_value(value)
    digits = strip_prefix(text, prefix)

    identifier = normalize_id(digits) if DIGITS_PATTERN.match(digits) else None
    if identifier is None:
        expected = f"{prefix!r} followed by digits" if prefix else "digits only"
        raise NormalizationError(
            "invalid_identifier",
            f"{text!r} is not a valid identifier (expected {expected})",
        )

    return identifier


def identifier_sort_key(identifier):
    """
    orders identifiers naturally so ORD-9 sorts before ORD-10
    :param identifier: canonical identifier (integer or text)
    :returns: comparable tuple
    """
    if isinstance(identifier, int):
        return ((0, identifier, ""),)
    return tuple(
        (0, int(chunk), chunk) if chunk.isdigit() else (1, 0, chunk)
        for chunk in NATURAL_CHUNKS.split(str(identifier))
        if chunk
    ) + ((2, 0, str(identifier)),)


def parse_date(value, formats):
    """
    parses a calendar date using only the formats declared in the profile
    :param value: raw date text, or a native date from a spreadsheet cell
    :param formats: ordered strptime formats declared by the profile
    :returns: calendar date as written in the source (no time zone conversion)
    """
    if is_blank(value):
        raise NormalizationError("missing_date", "date is blank")

    # native spreadsheet dates are typed values, so they carry no ambiguity
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = display_value(value)
    matches = {}
    calendar_errors = []
    for date_format in formats:
        try:
            parsed = datetime.strptime(text, date_format)
        except ValueError as error:
            # shape mismatches say "time data ..." or "unconverted data ...";
            # anything else means the shape matched but the date is impossible
            message = str(error)
            if not message.startswith(("time data", "unconverted data")):
                calendar_errors.append(date_format)
            continue
        # an offset such as -0400 is kept as written; the local calendar date
        # is used and timestamps are never shifted into another time zone
        matches.setdefault(parsed.date(), []).append(date_format)

    if len(matches) > 1:
        readings = ", ".join(
            f"{day.isoformat()} via {formats_used[0]}"
            for day, formats_used in sorted(matches.items())
        )
        raise NormalizationError(
            "ambiguous_date",
            f"{text!r} matches several declared formats with different dates "
            f"({readings})",
        )

    if matches:
        return next(iter(matches))

    if calendar_errors:
        raise NormalizationError(
            "invalid_calendar_date",
            f"{text!r} is not a real calendar date",
        )

    raise NormalizationError(
        "invalid_date",
        f"{text!r} does not match any declared date format {list(formats)}",
    )


def amount_pattern(rules):
    """
    builds the strict number pattern implied by the profile separators
    :param rules: amount rules from the profile
    :returns: compiled regular expression with integer and fraction groups
    """
    decimal = re.escape(rules.decimal_separator)
    if rules.thousands_separator:
        thousands = re.escape(rules.thousands_separator)
        integer = rf"(?:[0-9]{{1,3}}(?:{thousands}[0-9]{{3}})+|[0-9]+)"
    else:
        integer = r"[0-9]+"
    return re.compile(rf"^(?P<integer>{integer})(?:{decimal}(?P<fraction>[0-9]+))?$")


def check_amount(amount, text, rules):
    """
    applies precision and range limits to a parsed amount
    :param amount: parsed decimal amount
    :param text: original value used in messages
    :param rules: amount rules from the profile
    :returns: amount quantized to cents
    """
    if not amount.is_finite():
        raise NormalizationError("invalid_amount", f"{text!r} is not a finite amount")

    exponent = amount.as_tuple().exponent
    if isinstance(exponent, int) and -exponent > rules.max_decimal_places:
        raise NormalizationError(
            "too_many_decimal_places",
            f"{text!r} has more than {rules.max_decimal_places} decimal places",
        )

    if abs(amount) > MAX_FINANCIAL_AMOUNT:
        raise NormalizationError(
            "amount_out_of_range",
            f"{text!r} exceeds the supported maximum of {MAX_FINANCIAL_AMOUNT}",
        )

    return amount.quantize(CENT)


def parse_amount(value, rules):
    """
    parses a monetary amount exactly using the profile's declared conventions
    :param value: raw amount text, or a native number from a spreadsheet cell
    :param rules: amount rules from the profile
    :returns: decimal amount at cent precision
    """
    if is_blank(value):
        raise NormalizationError("missing_amount", "amount is blank")

    if isinstance(value, bool):
        raise NormalizationError("invalid_amount", "amount is not a number")

    if isinstance(value, (int, Decimal)):
        return check_amount(Decimal(value), display_value(value), rules)

    if isinstance(value, float):
        # spreadsheet numbers arrive as binary floats; repr gives the shortest
        # decimal that round-trips, which is what the spreadsheet displayed
        try:
            amount = Decimal(repr(value))
        except InvalidOperation as error:
            raise NormalizationError(
                "invalid_amount", f"{value!r} is not a valid amount"
            ) from error
        return check_amount(amount, repr(value), rules)

    original = display_value(value)
    text = original
    negative = False

    if text.startswith("(") and text.endswith(")"):
        if "parentheses" not in rules.negative_styles:
            raise NormalizationError(
                "invalid_amount",
                f"{original!r} uses parentheses for a negative amount, which this "
                "profile does not allow",
            )
        negative = True
        text = text[1:-1].strip()

    text, negative = strip_minus(text, negative, original, rules)

    for symbol in rules.currency_symbols:
        if text.startswith(symbol):
            text = text[len(symbol) :].strip()
            break
        if text.endswith(symbol):
            text = text[: -len(symbol)].strip()
            break

    text, negative = strip_minus(text, negative, original, rules)

    match = amount_pattern(rules).match(text)
    if not match:
        grouping = (
            f"{rules.thousands_separator!r} for thousands and "
            if rules.thousands_separator
            else ""
        )
        raise NormalizationError(
            "invalid_amount",
            f"{original!r} is not a valid amount (expected {grouping}"
            f"{rules.decimal_separator!r} for decimals"
            + (
                f", optional symbol {list(rules.currency_symbols)}"
                if rules.currency_symbols
                else ""
            )
            + ")",
        )

    integer = match.group("integer")
    if rules.thousands_separator:
        integer = integer.replace(rules.thousands_separator, "")
    fraction = match.group("fraction")
    canonical = integer + (f".{fraction}" if fraction is not None else "")
    amount = Decimal(canonical)
    if negative:
        amount = -amount

    return check_amount(amount, original, rules)


def strip_minus(text, negative, original, rules):
    """
    removes a leading minus sign when the profile allows it
    :param text: amount text being parsed
    :param negative: whether a negative marker was already found
    :param original: original value used in messages
    :param rules: amount rules from the profile
    :returns: tuple of remaining text and updated negative flag
    """
    if not text.startswith("-"):
        return text, negative

    if "minus" not in rules.negative_styles:
        raise NormalizationError(
            "invalid_amount",
            f"{original!r} uses a minus sign, which this profile does not allow",
        )
    if negative:
        raise NormalizationError(
            "invalid_amount", f"{original!r} has more than one negative marker"
        )

    return text[1:].strip(), True


def parse_currency(value, expected):
    """
    checks a source currency code against the profile currency
    :param value: raw currency code
    :param expected: currency declared by the profile
    :returns: normalized currency code
    """
    if is_blank(value):
        raise NormalizationError("missing_currency", "currency is blank")

    code = display_value(value).upper()
    if code != expected:
        raise NormalizationError(
            "currency_mismatch",
            f"{code!r} does not match the profile currency {expected!r}; "
            "currencies are never converted",
        )

    return code
