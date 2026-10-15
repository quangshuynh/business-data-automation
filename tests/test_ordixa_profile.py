import copy
import tomllib
from pathlib import Path

import pytest

from app.ordixa.profile import ProfileError, load_profile, validate_profile_document

PROFILE_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "ordixa"
    / "profiles"
    / "harbor-lane.toml"
)


@pytest.fixture
def document():
    """
    provides a mutable copy of the example profile document
    :returns: parsed TOML dictionary
    """
    with PROFILE_PATH.open("rb") as handle:
        return copy.deepcopy(tomllib.load(handle))


def problems_for(document):
    """
    validates a document that is expected to be invalid
    :param document: parsed profile dictionary
    :returns: list of reported problems
    """
    with pytest.raises(ProfileError) as error:
        validate_profile_document(document)
    return error.value.problems


def test_example_profile_loads():
    """
    tests that the shipped example profile is valid and fully parsed
    :returns: none
    """
    profile = load_profile(PROFILE_PATH)

    assert profile.name == "harbor-lane"
    assert profile.version == "1.0.0"
    assert profile.formats == {"csv", "xlsx"}
    assert profile.amounts.currency == "USD"
    assert profile.amounts.negative_styles == {"minus", "parentheses"}
    assert len(profile.sha256) == 64
    assert set(profile.datasets) == {"customers", "orders", "payments"}

    payments = profile.datasets["payments"]
    assert payments.refund_amounts == "negative"
    assert payments.id_prefixes == {"payment_id": "PMT-", "order_id": "#"}
    assert payments.value_maps["status"]["partially paid"] == "partial"
    assert payments.excluded_statuses == {"failed", "voided"}
    assert profile.datasets["customers"].columns["name"] == ("First Name", "Last Name")
    assert profile.datasets["customers"].required is False


def test_missing_profile_file_is_actionable(tmp_path):
    """
    tests that a missing profile path produces a profile error
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    with pytest.raises(ProfileError, match="cannot read profile"):
        load_profile(tmp_path / "absent.toml")


def test_toml_syntax_error_is_reported(tmp_path):
    """
    tests that malformed TOML is reported as a profile error
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    path = tmp_path / "broken.toml"
    path.write_text("[profile\nname = 'x'", encoding="utf-8")

    with pytest.raises(ProfileError, match="TOML syntax error"):
        load_profile(path)


def test_unknown_keys_suggest_corrections(document):
    """
    tests that misspelled keys are rejected with a suggestion
    :param document: example profile document
    :returns: none
    """
    orders = document["datasets"]["orders"]
    orders["colums"] = orders.pop("columns")

    problems = problems_for(document)

    assert any("datasets.orders.colums" in p and "'columns'" in p for p in problems)
    assert any("orders.columns: required table is missing" in p for p in problems)


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda d: d.update(schema_version=2), "schema_version: must be 1"),
        (lambda d: d["profile"].update(version="v1"), "MAJOR.MINOR.PATCH"),
        (lambda d: d["profile"].update(name="Bad Name"), "profile.name"),
        (lambda d: d["input"].update(formats=["json"]), "'json' is not supported"),
        (lambda d: d["amounts"].update(currency="usd"), "three-letter ISO"),
        (
            lambda d: d["amounts"].update(decimal_separator=","),
            "must differ",
        ),
        (lambda d: d["amounts"].update(max_decimal_places=3), "cent precision"),
        (lambda d: d["amounts"].update(currency_symbols=["$1"]), "may not contain"),
        (lambda d: d["amounts"].update(negative_styles=["red"]), "'red' is not one"),
        (
            lambda d: d["reconciliation"].update(missing_customer="ignore"),
            "missing_customer",
        ),
        (lambda d: d["datasets"].pop("payments"), "datasets.payments: required"),
        (
            lambda d: d["datasets"]["orders"]["columns"].pop("total"),
            "orders.columns.total: required field",
        ),
        (
            lambda d: d["datasets"]["orders"]["columns"].update(total="Created at"),
            "already mapped",
        ),
        (
            lambda d: d["datasets"]["orders"].update(date_formats=["%d/%m/%y"]),
            "four-digit year",
        ),
        (
            lambda d: d["datasets"]["orders"].update(date_formats=[]),
            "dates are never guessed",
        ),
        (
            lambda d: d["datasets"]["orders"].update(files=["../orders.csv"]),
            "without directories",
        ),
        (
            lambda d: d["datasets"]["orders"].update(files=["orders.json"]),
            "accepted format extension",
        ),
        (
            lambda d: d["datasets"]["payments"]["value_maps"]["status"].update(
                Chargeback="disputed"
            ),
            "'disputed' is not a supported status",
        ),
        (
            lambda d: d["datasets"]["payments"]["value_maps"]["status"].update(
                {"PAID ": "pending"}
            ),
            "conflicts with another mapping",
        ),
        (
            lambda d: d["datasets"]["payments"].update(excluded_statuses=["Pending"]),
            "also mapped in value_maps.status",
        ),
        (
            lambda d: d["datasets"]["payments"].update(refund_amounts="unsigned"),
            "refund_amounts",
        ),
        (
            lambda d: d["datasets"]["orders"].update(refund_amounts="negative"),
            "only applies to the payments dataset",
        ),
        (
            lambda d: d["datasets"]["orders"].update(optional_columns=["Total"]),
            "feeds a required field",
        ),
        (
            lambda d: d["datasets"]["orders"]["id_prefixes"].update(payment_id="P"),
            "orders.id_prefixes.payment_id: unsupported key",
        ),
        (
            lambda d: d["datasets"]["orders"].update(required=False),
            "cannot be optional",
        ),
    ],
)
def test_invalid_profiles_are_rejected(document, mutate, expected):
    """
    tests that unsupported profile configurations fail with explanations
    :param document: example profile document
    :param mutate: function applying an invalid change
    :param expected: substring expected in one of the reported problems
    :returns: none
    """
    mutate(document)

    problems = problems_for(document)

    assert any(expected in problem for problem in problems), problems


def test_all_problems_are_reported_together(document):
    """
    tests that validation reports every problem instead of stopping at the first
    :param document: example profile document
    :returns: none
    """
    document["amounts"]["currency"] = "dollars"
    document["profile"]["version"] = "latest"

    problems = problems_for(document)

    assert len(problems) == 2


def test_status_without_value_map_accepts_only_canonical_values(document):
    """
    tests that omitting a value map does not invent mappings
    :param document: example profile document
    :returns: none
    """
    del document["datasets"]["payments"]["value_maps"]
    del document["datasets"]["payments"]["excluded_statuses"]

    profile = validate_profile_document(document)

    assert profile.datasets["payments"].value_maps == {}
