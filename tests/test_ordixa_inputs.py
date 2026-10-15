from datetime import date, datetime
from decimal import Decimal

import pytest
from openpyxl import Workbook
from ordixa_helpers import EXPORTS_DIR, build_profile, copy_exports, csv_to_xlsx

from app.ordixa.adapters import discover_inputs, read_table
from app.ordixa.issues import InputError
from app.ordixa.mapping import canonicalize


def load_records(path, role, profile):
    """
    reads and canonicalizes one input file
    :param path: input file path
    :param role: dataset role
    :param profile: validated profile
    :returns: list of canonical records
    """
    spec = profile.datasets[role]
    return canonicalize(read_table(path, spec, profile), spec, profile)


def issue_codes(records):
    """
    collects issue codes by record reference
    :param records: canonical records
    :returns: mapping of record reference to issue codes
    """
    return {
        record.ref: [issue.code for issue in record.issues]
        for record in records
        if record.issues
    }


def test_discover_inputs_assigns_files_to_roles(tmp_path):
    """
    tests profile file patterns and ignored files
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = copy_exports("clean", tmp_path / "in")
    (input_dir / "notes.txt").write_text("not an export", encoding="utf-8")

    found, ignored = discover_inputs(input_dir, build_profile())

    assert [path.name for path in found["orders"]] == [
        "orders_2026-08.csv",
        "orders_2026-09.csv",
    ]
    assert [path.name for path in found["customers"]] == ["customers.csv"]
    assert len(found["payments"]) == 2
    assert ignored == ["notes.txt"]


def test_missing_required_dataset_is_reported(tmp_path):
    """
    tests that a required role without files stops the run
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = copy_exports("clean", tmp_path / "in", {"orders_2026-08.csv"})

    with pytest.raises(InputError, match="no payments file found"):
        discover_inputs(input_dir, build_profile())


def test_optional_customer_dataset_may_be_absent(tmp_path):
    """
    tests that the optional customers role can be omitted
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = copy_exports(
        "clean", tmp_path / "in", {"orders_2026-08.csv", "payments_2026-08.csv"}
    )

    found, _ = discover_inputs(input_dir, build_profile())

    assert found["customers"] == []


def test_overlapping_file_patterns_are_rejected(tmp_path):
    """
    tests that a file claimed by two roles is never read twice
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    input_dir = copy_exports("clean", tmp_path / "in")
    profile = build_profile(lambda d: d["datasets"]["payments"].update(files=["*.csv"]))

    with pytest.raises(InputError, match="matches the file patterns of both"):
        discover_inputs(input_dir, profile)


def test_missing_input_directory(tmp_path):
    """
    tests a missing input directory
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    with pytest.raises(InputError, match="input directory not found"):
        discover_inputs(tmp_path / "absent", build_profile())


def test_missing_column_reports_close_match(tmp_path):
    """
    tests that a renamed column produces an actionable message
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    source = (EXPORTS_DIR / "clean" / "orders_2026-08.csv").read_text("utf-8")
    path = tmp_path / "orders.csv"
    path.write_text(source.replace(",Total,", ",Order Total,"), encoding="utf-8")
    profile = build_profile()

    with pytest.raises(InputError, match=r"'Total' \(found 'Order Total'\)"):
        read_table(path, profile.datasets["orders"], profile)


def test_optional_source_column_may_be_absent(tmp_path):
    """
    tests that columns listed as optional may be missing from a file
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    path = tmp_path / "orders.csv"
    path.write_text(
        "Name,Created at,Customer ID,Total\n#1,2026-08-01,7000101,10.00\n",
        encoding="utf-8",
    )
    profile = build_profile(
        lambda d: d["datasets"]["orders"].update(optional_columns=["Currency"])
    )

    records = load_records(path, "orders", profile)

    assert records[0].accepted
    assert records[0].fields["total"] == Decimal("10.00")


def test_duplicate_headers_are_rejected(tmp_path):
    """
    tests duplicate header detection
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    path = tmp_path / "orders.csv"
    path.write_text(
        "Name,Created at,Customer ID,Currency,Total,Total\n", encoding="utf-8"
    )
    profile = build_profile()

    with pytest.raises(InputError, match="duplicate column headers"):
        read_table(path, profile.datasets["orders"], profile)


def test_ragged_csv_row_is_rejected_not_shifted(tmp_path):
    """
    tests that a row with extra cells is rejected rather than misaligned
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    path = tmp_path / "orders.csv"
    path.write_text(
        "Name,Created at,Customer ID,Currency,Total\n"
        "#1,2026-08-01,7000101,USD,10.00\n"
        "#2,2026-08-01,7000101,USD,1,000.00\n",
        encoding="utf-8",
    )
    profile = build_profile()

    records = load_records(path, "orders", profile)

    assert records[0].accepted
    assert records[1].row == 3
    assert [issue.code for issue in records[1].issues] == ["malformed_row"]


def test_xlsx_and_csv_inputs_produce_identical_canonical_data(tmp_path):
    """
    tests that the same export yields the same canonical rows from both formats
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    profile = build_profile()
    for name, role in [
        ("orders_2026-09.csv", "orders"),
        ("payments_2026-09.csv", "payments"),
        ("customers.csv", "customers"),
    ]:
        csv_path = EXPORTS_DIR / "problematic" / name
        xlsx_path = csv_to_xlsx(csv_path, tmp_path / name.replace(".csv", ".xlsx"))

        from_csv = load_records(csv_path, role, profile)
        from_xlsx = load_records(xlsx_path, role, profile)

        assert [(r.row, r.fields, issue_codes([r])) for r in from_csv] == [
            (r.row, r.fields, issue_codes([r])) for r in from_xlsx
        ]


def test_xlsx_typed_cells_are_used_without_guessing(tmp_path):
    """
    tests native date and numeric spreadsheet cells
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Orders"
    sheet.append(["Name", "Created at", "Customer ID", "Currency", "Total"])
    sheet.append(["#1", datetime(2026, 8, 3, 22, 15), 7000101, "USD", 129.99])
    sheet.append(["#2", date(2026, 8, 4), 7000101, "USD", 10.005])
    sheet.append([None, None, None, None, None])
    path = tmp_path / "orders.xlsx"
    workbook.save(path)
    profile = build_profile(lambda d: d["datasets"]["orders"].update(sheet="Orders"))

    records = load_records(path, "orders", profile)

    assert len(records) == 2
    assert records[0].fields["date"] == date(2026, 8, 3)
    assert records[0].fields["total"] == Decimal("129.99")
    assert records[0].fields["customer_id"] == 7000101
    assert records[1].fields["date"] == date(2026, 8, 4)
    assert [issue.code for issue in records[1].issues] == ["too_many_decimal_places"]


def test_xlsx_missing_sheet_is_reported(tmp_path):
    """
    tests a profile sheet name that is absent from the workbook
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    path = csv_to_xlsx(
        EXPORTS_DIR / "clean" / "orders_2026-08.csv", tmp_path / "orders.xlsx"
    )
    profile = build_profile(lambda d: d["datasets"]["orders"].update(sheet="Orders"))

    with pytest.raises(InputError, match="no worksheet named 'Orders'"):
        read_table(path, profile.datasets["orders"], profile)


def test_corrupt_xlsx_is_reported(tmp_path):
    """
    tests that a file with an xlsx extension but invalid content is rejected
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    path = tmp_path / "orders.xlsx"
    path.write_bytes(b"not a workbook")
    profile = build_profile()

    with pytest.raises(InputError, match="could not be opened as XLSX"):
        read_table(path, profile.datasets["orders"], profile)


def test_status_and_type_mapping_is_explicit_and_case_insensitive(tmp_path):
    """
    tests mapped, unmapped, and excluded payment labels
    :param tmp_path: pytest temporary directory
    :returns: none
    """
    path = tmp_path / "payments.csv"
    path.write_text(
        "Transaction ID,Order Reference,Date,Type,Status,Amount,Currency\n"
        "PMT-1,#1,08/01/2026,PAYMENT,  partially   paid ,$5.00,USD\n"
        "PMT-2,#1,08/01/2026,Payment,Disputed,$5.00,USD\n"
        "PMT-3,#1,08/01/2026,Chargeback,Paid,$5.00,USD\n"
        "PMT-4,#1,08/01/2026,Payment,VOIDED,$5.00,USD\n"
        "PMT-5,#1,08/01/2026,Refund,Refunded,-$2.00,USD\n",
        encoding="utf-8",
    )

    records = load_records(path, "payments", build_profile())
    by_ref = {record.ref: record for record in records}

    assert by_ref["PMT-1"].fields["status"] == "partial"
    assert by_ref["PMT-1"].fields["transaction_type"] == "payment"
    assert issue_codes(records) == {
        "PMT-2": ["unmapped_status"],
        "PMT-3": ["unmapped_transaction_type"],
        "PMT-4": ["excluded_status"],
    }
    assert by_ref["PMT-4"].excluded and not by_ref["PMT-4"].rejected
    assert by_ref["PMT-5"].fields["amount"] == Decimal("2.00")


def test_customer_contact_problems_are_warnings_only():
    """
    tests that optional contact data never rejects a customer
    :returns: none
    """
    profile = build_profile()
    records = load_records(
        EXPORTS_DIR / "problematic" / "customers.csv", "customers", profile
    )
    by_ref = {record.ref: record for record in records}

    for ref, code in [
        ("7000102", "invalid_email"),
        ("7000103", "missing_phone"),
        ("7000104", "missing_name"),
        ("7000107", "invalid_phone"),
    ]:
        assert by_ref[ref].accepted
        assert [issue.code for issue in by_ref[ref].issues] == [code]
        assert not any(issue.blocking for issue in by_ref[ref].issues)

    assert by_ref["ABC-17"].rejected
    assert by_ref["7000107"].fields["phone"] == "+44 20 7946 0107"
