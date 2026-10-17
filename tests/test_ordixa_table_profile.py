"""
tests for clean/compare table profiles and their separation from
reconciliation profiles
"""

import pytest
from ordixa_helpers import PROFILE_PATH
from table_helpers import CLEAN_PROFILE, COMPARE_PROFILE, table_profile

from app.ordixa.profile import ProfileError, load_profile
from app.ordixa.tabular_profile import load_table_profile


def problems_for(kind="compare", mutate=None, **table):
    """
    collects validation problems for a modified test profile
    :param kind: clean or compare
    :param mutate: function editing the document
    :param table: overrides for the [table] section
    :returns: newline-joined problems
    """
    with pytest.raises(ProfileError) as caught:
        table_profile(kind, mutate, **table)
    return "\n".join(caught.value.problems)


def test_example_profiles_load():
    """
    tests that the shipped inventory profiles are valid and ordered
    :returns: none
    """
    clean = load_table_profile(CLEAN_PROFILE, "clean")
    compare = load_table_profile(COMPARE_PROFILE, "compare")

    assert clean.kind == "clean" and compare.kind == "compare"
    assert [c.name for c in clean.columns] == [
        "sku",
        "product_name",
        "category",
        "unit_price",
        "quantity_on_hand",
        "supplier",
        "last_counted",
    ]
    assert compare.key == ("sku",)
    assert compare.ignore == ("last_counted",)
    assert len(clean.sha256) == 64


def test_key_columns_are_always_required():
    """
    tests that key columns are required even when the column table omits it
    :returns: none
    """

    def optional_key(document):
        document["columns"]["sku"].pop("required")

    profile = table_profile(mutate=optional_key)
    assert profile.column("sku").required
    assert "SKU" not in profile.read_spec("before").optional_columns


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda d: d["columns"]["qty"].update(type="float"),
            "columns.qty.type: must be one of",
        ),
        (
            lambda d: d["table"].update(key=["price"]),
            "business keys must be identifier or text columns",
        ),
        (
            lambda d: d["table"].update(key=["qty"]),
            "business keys must be identifier or text columns",
        ),
        (lambda d: d["table"].update(key=["missing"]), "'missing' is not a mapped"),
        (lambda d: d["table"].update(key=[]), "required for compare"),
        (
            lambda d: d["columns"]["qty"].update(source="SKU"),
            "'SKU' is already mapped to 'sku'",
        ),
        (lambda d: d["table"].pop("date_formats"), "dates are never guessed"),
        (lambda d: d["table"].update(date_formats=["%d/%m/%y"]), "four-digit year"),
        (lambda d: d.pop("amounts"), "amounts: required table is missing"),
        (lambda d: d["columns"].update({"Bad Name": {"source": "X"}}), "lowercase"),
        (lambda d: d["table"].update(colour="x"), "table.colour: unsupported key"),
        (lambda d: d.update(compare={"ignore": ["sku"]}), "is a key column"),
        (lambda d: d.update(compare={"ignore": ["nope"]}), "'nope' is not a mapped"),
        (
            lambda d: d["columns"]["price"].update(whitespace="collapse"),
            "only text columns can collapse",
        ),
        (lambda d: d["table"].update(blank_values=[" N/A"]), "surrounding spaces"),
        (lambda d: d["amounts"].update(max_decimal_places=4), "from 0 to 2"),
        (lambda d: d["workflow"].update(kind="merge"), "workflow.kind: must be"),
    ],
)
def test_invalid_profiles_are_rejected(mutate, expected):
    """
    tests that ambiguous or unsafe profile settings are refused with a reason
    :param mutate: function editing the document
    :param expected: text expected among the problems
    :returns: none
    """
    assert expected in problems_for(mutate=mutate)


def test_amounts_only_with_decimal_columns():
    """
    tests that an [amounts] section needs a decimal column to apply to
    :returns: none
    """

    def no_decimals(document):
        document["columns"]["price"]["type"] = "text"

    assert "only allowed when a decimal column" in problems_for(mutate=no_decimals)


def test_compare_section_is_refused_in_clean_profiles():
    """
    tests that compare settings cannot hide in a clean profile
    :returns: none
    """

    def add_compare(document):
        document["compare"] = {"ignore": ["counted"]}

    assert "only allowed when workflow.kind" in problems_for("clean", add_compare)


def test_clean_profiles_do_not_need_a_key():
    """
    tests that cleaning works without a business key
    :returns: none
    """
    assert table_profile("clean", key=[]).key == ()


def test_profile_kinds_reject_each_other(tmp_path):
    """
    tests that reconciliation and table profiles are never run by the wrong
    command, and that a clean profile is not accepted by compare
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    with pytest.raises(ProfileError, match="use python -m app.ordixa run"):
        load_table_profile(PROFILE_PATH)
    with pytest.raises(ProfileError, match="clean/compare profile"):
        load_profile(CLEAN_PROFILE)
    with pytest.raises(ProfileError, match="this profile is for clean, not compare"):
        load_table_profile(CLEAN_PROFILE, "compare")


def test_reconciliation_profiles_are_unchanged():
    """
    tests that existing reconciliation profiles still load as before
    :returns: none
    """
    profile = load_profile(PROFILE_PATH)
    assert profile.name == "harbor-lane"
    assert set(profile.datasets) == {"customers", "orders", "payments"}
