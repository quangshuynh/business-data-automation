import re
from datetime import date, datetime
from decimal import Decimal

import pandas as pd
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.ordixa.issues import OUTCOME_LABELS
from app.ordixa.normalize import identifier_sort_key

SHEET_NAMES = ("Summary", "Exceptions", "Rejected Rows", "Full Ledger")

# Ordixa palette: deep navy headers with white text, muted slate for labels;
# every foreground/background pair below exceeds a 7:1 contrast ratio
NAVY = "1F2A44"
SLATE = "334155"
RULE = "CBD5E1"
WHITE = "FFFFFF"
STATUS_STYLES = {
    "paid": ("Paid", "E6F4EA", "14532D"),
    "partial": ("Partially paid", "FFF4D6", "713F12"),
    "unpaid": ("Unpaid", "FDE2E1", "7F1D1D"),
    "overpaid": ("Overpaid", "E3ECFA", "1E3A8A"),
}
SEVERITY_STYLES = {
    "error": ("FDE2E1", "7F1D1D"),
    "warning": ("FFF4D6", "713F12"),
    "excluded": ("EEF2F7", "1F2A44"),
}

MONEY_FORMAT = "#,##0.00;-#,##0.00"
DATE_FORMAT = "yyyy-mm-dd"
INTEGER_FORMAT = "#,##0"

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n", "＝", "＋")
# Excel stores numbers as binary doubles and openpyxl writes them through float
# repr, so only values with at most 15 significant digits survive exactly
EXCEL_SAFE_DIGITS = 15
MAX_CELL_TEXT = 32_767
TRUNCATION_MARK = " [truncated]"
# identifiers are always text cells so leading zeros and long numbers survive
TEXT_COLUMNS = {"order_id", "customer_id", "record_id", "order_ref"}
PLAIN_NUMBER = re.compile(r"^[-+]?[$€£¥]?\s?[0-9][0-9.,\s]*$")

HEADER_FONT = Font(bold=True, color=WHITE)
HEADER_FILL = PatternFill("solid", fgColor=NAVY)
TITLE_FONT = Font(bold=True, size=16, color=NAVY)
SECTION_FONT = Font(bold=True, size=12, color=NAVY)
LABEL_FONT = Font(color=SLATE)
BOTTOM_RULE = Border(bottom=Side(style="thin", color=RULE))

LEDGER_HEADERS = {
    "order_ref": "Order",
    "order_id": "Order ID",
    "order_date": "Order date",
    "customer_id": "Customer ID",
    "customer_name": "Customer",
    "customer_email": "Customer email",
    "customer_found": "Customer on file",
    "order_total": "Order total",
    "payments_received": "Payments",
    "refunds": "Refunds",
    "adjustments": "Adjustments",
    "net_paid": "Net paid",
    "balance_due": "Balance due",
    "outstanding_balance": "Outstanding",
    "overpayment_amount": "Overpaid",
    "financial_status": "Status",
    "discrepancy_flags": "Discrepancy flags",
    "transaction_count": "Transactions",
    "transaction_refs": "Transaction IDs",
    "last_payment_date": "Last payment date",
    "source_location": "Source",
}
EXCEPTION_COLUMNS = [
    "exception_type",
    "order_ref",
    "order_date",
    "customer_name",
    "financial_status",
    "order_total",
    "net_paid",
    "outstanding_balance",
    "overpayment_amount",
    "transaction_count",
    "transaction_refs",
    "discrepancy_flags",
    "source_location",
]
EXCEPTION_ORDER = {
    "Unpaid": 0,
    "Partially paid": 1,
    "Overpaid": 2,
    "Paid with discrepancy": 3,
}
MONEY_COLUMNS = {
    "order_total",
    "payments_received",
    "refunds",
    "adjustments",
    "net_paid",
    "balance_due",
    "outstanding_balance",
    "overpayment_amount",
}


def safe_text(value):
    """
    neutralizes untrusted text so spreadsheet tools never evaluate it

    text that could start a formula gets a leading apostrophe, except values
    that are plainly numbers such as -$89.00; XML-illegal control characters
    are removed
    :param value: untrusted text
    :returns: sanitized text
    """
    text = ILLEGAL_CHARACTERS_RE.sub("", str(value))
    if text.startswith(FORMULA_PREFIXES) and not PLAIN_NUMBER.match(text):
        return "'" + text
    return text


def exact_in_excel(value):
    """
    checks whether a number can be stored as an Excel number without losing
    digits
    :param value: decimal or integer
    :returns: true when at most 15 significant digits are needed
    """
    if isinstance(value, Decimal):
        return value.is_finite() and len(value.as_tuple().digits) <= EXCEL_SAFE_DIGITS
    return abs(value) < 10**EXCEL_SAFE_DIGITS


def imprecise_amounts(result):
    """
    counts monetary values too precise for an Excel number cell
    :param result: run result
    :returns: number of summary and ledger values written as exact text
    """
    values = list(result.summary.values())
    for row in result.ledger.to_dict(orient="records"):
        values.extend(row[column] for column in MONEY_COLUMNS)
    return sum(
        1
        for value in values
        if isinstance(value, Decimal) and not exact_in_excel(value)
    )


def cell_text(value):
    """
    sanitizes text for a cell and keeps it within Excel's length limit
    :param value: untrusted text
    :returns: text no longer than 32,767 characters
    """
    text = safe_text(value)
    if len(text) > MAX_CELL_TEXT:
        text = text[: MAX_CELL_TEXT - len(TRUNCATION_MARK)] + TRUNCATION_MARK
    return text


def status_label(status):
    """
    converts a canonical financial status into its display label
    :param status: canonical status
    :returns: display label
    """
    return STATUS_STYLES.get(status, (str(status).title(), None, None))[0]


def write_cell(sheet, row, column, value, column_name=None):
    """
    writes one value with a type-appropriate number format
    :param sheet: worksheet
    :param row: row number
    :param column: column number
    :param value: python value
    :param column_name: canonical column name used to detect money columns
    :returns: written cell
    """
    cell = sheet.cell(row=row, column=column)

    if value is None or (not isinstance(value, str) and pd.isna(value)):
        cell.value = None
    elif isinstance(value, bool):
        cell.value = "Yes" if value else "No"
    elif column_name in TEXT_COLUMNS:
        cell.value = cell_text(value)
        cell.data_type = "s"
    elif isinstance(value, (Decimal, int)) and not exact_in_excel(value):
        # an Excel number would silently drop digits; keep the exact value as
        # right-aligned text instead (the Summary sheet counts these)
        cell.value = format(value, "f") if isinstance(value, Decimal) else str(value)
        cell.data_type = "s"
        cell.alignment = Alignment(horizontal="right")
    elif isinstance(value, Decimal):
        # at most 15 significant digits, so the float written by openpyxl
        # converts back to exactly this decimal
        cell.value = value
        cell.number_format = MONEY_FORMAT
    elif isinstance(value, int):
        cell.value = value
        cell.number_format = MONEY_FORMAT if column_name in MONEY_COLUMNS else "0"
    elif isinstance(value, datetime):
        cell.value = value.replace(tzinfo=None)
        cell.number_format = "yyyy-mm-dd hh:mm:ss"
    elif isinstance(value, date):
        cell.value = value
        cell.number_format = DATE_FORMAT
    else:
        cell.value = cell_text(value)
        cell.data_type = "s"

    return cell


def write_table(sheet, start_row, columns, headers, rows):
    """
    writes a header row and records as a filterable table
    :param sheet: worksheet
    :param start_row: row of the header
    :param columns: canonical column names
    :param headers: display headers in column order
    :param rows: list of dictionaries keyed by canonical column
    :returns: last row written
    """
    for index, header in enumerate(headers, start=1):
        cell = sheet.cell(row=start_row, column=index, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)

    row_number = start_row
    for record in rows:
        row_number += 1
        for index, column in enumerate(columns, start=1):
            cell = write_cell(sheet, row_number, index, record.get(column), column)
            if column == "financial_status" and record.get(column) in STATUS_STYLES:
                label, fill, color = STATUS_STYLES[record[column]]
                cell.value = label
                cell.fill = PatternFill("solid", fgColor=fill)
                cell.font = Font(color=color, bold=True)

    last_column = get_column_letter(len(columns))
    sheet.auto_filter.ref = f"A{start_row}:{last_column}{max(row_number, start_row)}"
    sheet.freeze_panes = sheet.cell(
        row=start_row + 1, column=2 if len(columns) > 3 else 1
    )
    return row_number


def fit_columns(sheet, minimum=9, maximum=60):
    """
    sizes columns to their content within readable limits
    :param sheet: worksheet
    :param minimum: smallest width
    :param maximum: largest width
    :returns: none
    """
    widths = {}
    for row in sheet.iter_rows():
        for cell in row:
            if cell.value is None:
                continue
            if isinstance(cell.value, Decimal):
                length = len(f"{cell.value:,.2f}") + 1
            elif isinstance(cell.value, (date, datetime)):
                length = 11
            else:
                length = max(len(line) for line in str(cell.value).splitlines() or [""])
            widths[cell.column_letter] = max(widths.get(cell.column_letter, 0), length)

    for letter, width in widths.items():
        sheet.column_dimensions[letter].width = max(minimum, min(maximum, width + 2))


def exception_type(row):
    """
    classifies a ledger row for the exceptions sheet
    :param row: ledger row dictionary
    :returns: exception label
    """
    if row["financial_status"] == "paid":
        return "Paid with discrepancy"
    return status_label(row["financial_status"])


def build_summary_sheet(sheet, result, metadata):
    """
    writes headline totals, quality counts, and processing metadata
    :param sheet: worksheet
    :param result: run result
    :param metadata: execution metadata for the run
    :returns: none
    """
    summary = result.summary
    profile = result.profile
    currency = profile.amounts.currency

    sheet["A1"] = "Ordixa reconciliation summary"
    sheet["A1"].font = TITLE_FONT
    sheet["A2"] = safe_text(
        f"Profile {profile.name} v{profile.version} - amounts in {currency}"
    )
    sheet["A2"].font = LABEL_FONT
    row = 4

    def section(title):
        nonlocal row
        cell = sheet.cell(row=row, column=1, value=title)
        cell.font = SECTION_FONT
        cell.border = BOTTOM_RULE
        sheet.cell(row=row, column=2).border = BOTTOM_RULE
        row += 1

    def line(label, value, number_format=None):
        nonlocal row
        sheet.cell(row=row, column=1, value=label).font = LABEL_FONT
        cell = write_cell(sheet, row, 2, value)
        if number_format:
            cell.number_format = number_format
        cell.alignment = Alignment(horizontal="right")
        row += 1

    section("Financial totals")
    line("Orders reconciled", summary["orders"], INTEGER_FORMAT)
    line("Order value", summary["order_value"])
    line("Transactions counted", summary["transactions"], INTEGER_FORMAT)
    line("Payments received", summary["payments_received"])
    line("Refunds (deducted)", summary["refunds"])
    line("Adjustments (signed)", summary["adjustments"])
    line("Net received", summary["net_received"])
    line("Reconciled to orders", summary["applied_to_orders"])
    line("Outstanding balances", summary["outstanding_balance"])
    line("Overpayments", summary["overpayments"])
    row += 1

    section("Exceptions")
    for status in ("unpaid", "partial", "overpaid"):
        line(f"{status_label(status)} orders", summary["status_counts"][status])
    line("Orders with discrepancy flags", summary["flagged_orders"])
    line("Orders needing review", summary["exception_orders"])
    line("Paid orders", summary["status_counts"]["paid"])
    row += 1

    section("Data quality")
    headers = [
        "Dataset",
        "Rows read",
        "Accepted",
        "With warnings",
        "Rejected",
        "Excluded",
    ]
    for index, header in enumerate(headers, start=1):
        cell = sheet.cell(row=row, column=index, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
    row += 1
    for dataset, counts in result.counts.items():
        values = [
            dataset.title(),
            counts["rows"],
            counts["accepted"],
            counts["accepted_with_warnings"],
            counts["rejected"],
            counts["excluded"],
        ]
        for index, value in enumerate(values, start=1):
            write_cell(sheet, row, index, value)
        row += 1
    row += 1

    section("Processing")
    line("Run ID", metadata["run_id"])
    line("Generated (UTC)", metadata["generated_at"])
    line("Profile", f"{profile.name} {profile.version}")
    line("Application version", metadata["code_version"])
    line("Status", metadata["status"])
    line("Rejected rows (blocking)", summary["rejected_rows"], INTEGER_FORMAT)
    line("Rows kept with warnings", summary["warning_rows"], INTEGER_FORMAT)
    line("Rows excluded by profile", summary["excluded_rows"], INTEGER_FORMAT)
    imprecise = imprecise_amounts(result)
    if imprecise:
        line("Amounts stored as exact text (over 15 digits)", imprecise, INTEGER_FORMAT)
    row += 1

    section("Input files")
    for index, header in enumerate(["Role", "File", "Rows", "SHA-256"], start=1):
        cell = sheet.cell(row=row, column=index, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
    row += 1
    for input_file in result.inputs:
        for index, value in enumerate(
            [input_file.role, input_file.name, input_file.data_rows, input_file.sha256],
            start=1,
        ):
            write_cell(sheet, row, index, value)
        row += 1

    fit_columns(sheet, maximum=40)
    sheet.column_dimensions["A"].width = 32
    sheet.column_dimensions["B"].width = 26
    sheet.sheet_view.showGridLines = False


def build_exceptions_sheet(sheet, result):
    """
    writes orders that need follow-up
    :param sheet: worksheet
    :param result: run result
    :returns: none
    """
    rows = []
    for row in result.exceptions.to_dict(orient="records"):
        rows.append({**row, "exception_type": exception_type(row)})
    rows.sort(
        key=lambda item: (
            EXCEPTION_ORDER[item["exception_type"]],
            identifier_sort_key(item["order_id"]),
        )
    )

    headers = ["Exception"] + [
        LEDGER_HEADERS[column] for column in EXCEPTION_COLUMNS[1:]
    ]
    write_table(sheet, 1, EXCEPTION_COLUMNS, headers, rows)
    fit_columns(sheet)


def build_rejected_rows_sheet(sheet, result):
    """
    writes every row-level issue with its source location and outcome
    :param sheet: worksheet
    :param result: run result
    :returns: none
    """
    columns = [
        "dataset",
        "file",
        "row",
        "record_id",
        "outcome",
        "blocking",
        "code",
        "field",
        "value",
        "message",
        "original_values",
    ]
    headers = [
        "Dataset",
        "Source file",
        "Source row",
        "Record ID",
        "Outcome",
        "Prevented processing",
        "Issue code",
        "Field",
        "Value",
        "Reason",
        "Original values",
    ]
    rows = [
        {
            "dataset": issue.dataset,
            "file": issue.file,
            "row": issue.row,
            "record_id": issue.record_id,
            "outcome": OUTCOME_LABELS[issue.severity],
            "blocking": issue.blocking,
            "code": issue.code,
            "field": issue.field,
            "value": issue.value,
            "message": issue.message,
            "original_values": issue.original_values,
        }
        for issue in result.issues
    ]
    last_row = write_table(sheet, 1, columns, headers, rows)

    for row_number, issue in zip(range(2, last_row + 1), result.issues):
        fill, color = SEVERITY_STYLES[issue.severity]
        cell = sheet.cell(row=row_number, column=5)
        cell.fill = PatternFill("solid", fgColor=fill)
        cell.font = Font(color=color, bold=True)

    fit_columns(sheet, maximum=70)


def build_ledger_sheet(sheet, result):
    """
    writes the full reconciled ledger
    :param sheet: worksheet
    :param result: run result
    :returns: none
    """
    columns = list(LEDGER_HEADERS)
    rows = result.ledger.to_dict(orient="records")
    write_table(sheet, 1, columns, [LEDGER_HEADERS[c] for c in columns], rows)
    fit_columns(sheet)


def write_workbook(result, path, metadata):
    """
    writes the exceptions workbook for a run
    :param result: run result
    :param path: destination .xlsx path
    :param metadata: execution metadata (run_id, generated_at, code_version, status)
    :returns: destination path
    """
    workbook = Workbook()
    summary_sheet = workbook.active
    summary_sheet.title = SHEET_NAMES[0]
    build_summary_sheet(summary_sheet, result, metadata)
    build_exceptions_sheet(workbook.create_sheet(SHEET_NAMES[1]), result)
    build_rejected_rows_sheet(workbook.create_sheet(SHEET_NAMES[2]), result)
    build_ledger_sheet(workbook.create_sheet(SHEET_NAMES[3]), result)

    workbook.properties.creator = "Ordixa"
    workbook.properties.title = safe_text(f"Ordixa run {metadata['run_id']}")
    workbook.save(path)
    return path
