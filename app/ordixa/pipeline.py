from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd

from app.ordixa.adapters import discover_inputs, read_table
from app.ordixa.issues import ERROR, EXCLUDED, WARNING
from app.ordixa.mapping import canonicalize
from app.ordixa.normalize import identifier_sort_key
from app.ordixa.validation import validate_records
from app.reconciliation.reconcile import build_report

ZERO = Decimal("0.00")
DATASET_ORDER = ("customers", "orders", "payments")
FINANCIAL_STATUSES = ("paid", "partial", "unpaid", "overpaid")

# stable ledger columns shared by the CSV artifact and the workbook
LEDGER_COLUMNS = [
    "order_ref",
    "order_id",
    "order_date",
    "customer_id",
    "customer_name",
    "customer_email",
    "customer_found",
    "order_total",
    "payments_received",
    "refunds",
    "adjustments",
    "net_paid",
    "balance_due",
    "outstanding_balance",
    "overpayment_amount",
    "financial_status",
    "discrepancy_flags",
    "transaction_count",
    "transaction_refs",
    "last_payment_date",
    "source_location",
]


class ReconciliationIntegrityError(RuntimeError):
    """error raised when reconciled totals fail an independent cross-check"""


@dataclass(frozen=True)
class InputFile:
    """fingerprint and size of one processed input file"""

    role: str
    name: str
    sha256: str
    data_rows: int


@dataclass
class RunResult:
    """everything produced by processing one set of exports"""

    profile: object
    input_dir: Path
    inputs: list
    ignored_files: list
    records: dict
    ledger: pd.DataFrame
    summary: dict
    counts: dict
    reconciled_at: datetime
    issues: list = field(default_factory=list)

    @property
    def exceptions(self):
        """
        selects ledger rows that need review
        :returns: dataframe of orders that are not cleanly paid
        """
        if self.ledger.empty:
            return self.ledger
        mask = (self.ledger["financial_status"] != "paid") | (
            self.ledger["discrepancy_flags"] != ""
        )
        return self.ledger[mask]


def accepted(records):
    """
    filters records that continue into reconciliation
    :param records: canonical records
    :returns: list of accepted records
    """
    return [record for record in records if record.accepted]


def identifier_column(frame, column, mode):
    """
    fixes the dtype of an identifier column before the engine joins on it
    :param frame: dataframe to adjust in place
    :param column: identifier column
    :param mode: numeric or text
    :returns: none
    """
    if mode == "numeric":
        # nullable integers keep guest orders (no customer) joinable
        frame[column] = frame[column].astype("Int64")
    else:
        # plain objects keep text identifiers exactly as normalized
        frame[column] = frame[column].astype(object)


def canonical_id(value):
    """
    converts an identifier read back from a dataframe into a plain value
    :param value: identifier cell
    :returns: integer, text, or none
    """
    if value is None or pd.isna(value):
        return None
    if isinstance(value, str):
        return value
    return int(value)


def build_frames(records, profile):
    """
    converts accepted canonical records into the existing engine's dataframes
    :param records: mapping of dataset role to canonical records
    :param profile: validated import profile
    :returns: tuple of customer, order, and payment dataframes
    """
    customers = pd.DataFrame(
        [
            {
                "customer_id": record.fields["customer_id"],
                "name": record.fields.get("name"),
                "email": record.fields.get("email"),
                "phone": record.fields.get("phone"),
            }
            for record in accepted(records.get("customers") or [])
        ],
        columns=["customer_id", "name", "email", "phone"],
    )
    orders = pd.DataFrame(
        [
            {
                "order_id": record.fields["order_id"],
                "customer_id": record.fields.get("customer_id"),
                "date": record.fields["date"],
                "total": record.fields["total"],
            }
            for record in accepted(records["orders"])
        ],
        columns=["order_id", "customer_id", "date", "total"],
    )
    payments = pd.DataFrame(
        [
            {
                "payment_id": record.fields["payment_id"],
                "order_id": record.fields["order_id"],
                "amount": record.fields["amount"],
                "transaction_type": record.fields["transaction_type"],
                "status": record.fields["status"],
            }
            for record in accepted(records["payments"])
        ],
        columns=["payment_id", "order_id", "amount", "transaction_type", "status"],
    )

    customer_mode = profile.identifier_mode("customer_id")
    order_mode = profile.identifier_mode("order_id")
    identifier_column(customers, "customer_id", customer_mode)
    identifier_column(orders, "customer_id", customer_mode)
    identifier_column(orders, "order_id", order_mode)
    identifier_column(payments, "order_id", order_mode)
    identifier_column(payments, "payment_id", profile.identifier_mode("payment_id"))
    return customers, orders, payments


def transaction_breakdown(payment_records):
    """
    totals accepted transactions per order independently of the engine
    :param payment_records: accepted canonical payment records
    :returns: mapping of order id to breakdown dictionary
    """
    breakdown = {}
    for record in payment_records:
        fields = record.fields
        entry = breakdown.setdefault(
            fields["order_id"],
            {
                "payment": ZERO,
                "refund": ZERO,
                "adjustment": ZERO,
                "refs": [],
                "last_date": None,
            },
        )
        entry[fields["transaction_type"]] += fields["amount"]
        entry["refs"].append(record.ref)
        if fields.get("payment_date") and (
            entry["last_date"] is None or fields["payment_date"] > entry["last_date"]
        ):
            entry["last_date"] = fields["payment_date"]
    return breakdown


def build_ledger(records, report, profile):
    """
    combines the engine report with source references and breakdowns
    :param records: mapping of dataset role to canonical records
    :param report: dataframe returned by the reconciliation engine
    :param profile: validated import profile
    :returns: ledger dataframe sorted by order id
    """
    orders = {
        record.fields["order_id"]: record for record in accepted(records["orders"])
    }
    breakdown = transaction_breakdown(accepted(records["payments"]))
    rows = []

    report_rows = report.to_dict(orient="records")
    report_rows.sort(key=lambda row: identifier_sort_key(canonical_id(row["order_id"])))
    for row in report_rows:
        order_id = canonical_id(row["order_id"])
        order = orders[order_id]
        entry = breakdown.get(
            order_id,
            {"payment": ZERO, "refund": ZERO, "adjustment": ZERO, "refs": []},
        )
        rows.append(
            {
                "order_ref": order.ref,
                "order_id": order_id,
                "order_date": row["date"],
                "customer_id": canonical_id(row["customer_id"]),
                "customer_name": None if pd.isna(row["name"]) else row["name"],
                "customer_email": None if pd.isna(row["email"]) else row["email"],
                "customer_found": bool(row["customer_found"]),
                "order_total": row["total"],
                "payments_received": entry["payment"],
                "refunds": entry["refund"],
                "adjustments": entry["adjustment"],
                "net_paid": row["amount_paid"],
                "balance_due": row["balance_due"],
                "outstanding_balance": row["outstanding_balance"],
                "overpayment_amount": row["overpayment_amount"],
                "financial_status": row["financial_status"],
                "discrepancy_flags": row["discrepancy_flags"],
                "transaction_count": int(row["payment_count"]),
                "transaction_refs": ", ".join(sorted(entry["refs"])),
                "last_payment_date": entry.get("last_date"),
                "source_location": f"{order.file} row {order.row}",
            }
        )

    ledger = pd.DataFrame(rows, columns=LEDGER_COLUMNS)
    identifier_column(ledger, "order_id", profile.identifier_mode("order_id"))
    identifier_column(ledger, "customer_id", profile.identifier_mode("customer_id"))
    return ledger


def verify_integrity(ledger, records):
    """
    cross-checks engine output against independent sums of accepted rows

    a failure means a row was dropped or counted twice, so the run is stopped
    rather than producing untrustworthy totals
    :param ledger: reconciled ledger
    :param records: mapping of dataset role to canonical records
    :returns: none
    """
    orders = accepted(records["orders"])
    payments = accepted(records["payments"])
    problems = []

    if len(ledger) != len(orders):
        problems.append(f"{len(ledger)} ledger rows for {len(orders)} accepted orders")

    signed = sum(
        (
            -record.fields["amount"]
            if record.fields["transaction_type"] == "refund"
            else record.fields["amount"]
            for record in payments
        ),
        ZERO,
    )
    if sum(ledger["net_paid"], ZERO) != signed:
        problems.append("ledger net paid does not equal the accepted transactions")

    if int(ledger["transaction_count"].sum()) != len(payments):
        problems.append("ledger transaction count does not match accepted rows")

    for row in ledger.to_dict(orient="records"):
        expected = row["payments_received"] - row["refunds"] + row["adjustments"]
        if expected != row["net_paid"]:
            problems.append(f"order {row['order_ref']}: breakdown != net paid")

    if problems:
        raise ReconciliationIntegrityError("; ".join(problems))


def summarize(ledger, records):
    """
    calculates run totals with exact decimal arithmetic
    :param ledger: reconciled ledger
    :param records: mapping of dataset role to canonical records
    :returns: summary dictionary
    """

    def total(column):
        return sum(ledger[column], ZERO) if not ledger.empty else ZERO

    statuses = Counter(ledger["financial_status"]) if not ledger.empty else Counter()
    applied = sum(
        (
            min(max(row["net_paid"], ZERO), row["order_total"])
            for row in ledger.to_dict(orient="records")
        ),
        ZERO,
    )
    issues = all_issues(records)
    flagged = int((ledger["discrepancy_flags"] != "").sum()) if len(ledger) else 0

    return {
        "orders": len(ledger),
        "order_value": total("order_total"),
        "transactions": int(ledger["transaction_count"].sum()) if len(ledger) else 0,
        "payments_received": total("payments_received"),
        "refunds": total("refunds"),
        "adjustments": total("adjustments"),
        "net_received": total("net_paid"),
        "applied_to_orders": applied,
        "outstanding_balance": total("outstanding_balance"),
        "overpayments": total("overpayment_amount"),
        "status_counts": {
            status: statuses.get(status, 0) for status in FINANCIAL_STATUSES
        },
        "exception_orders": int(
            (
                (ledger["financial_status"] != "paid")
                | (ledger["discrepancy_flags"] != "")
            ).sum()
        )
        if len(ledger)
        else 0,
        "flagged_orders": flagged,
        "rejected_rows": sum(
            1 for dataset in records.values() for r in dataset or [] if r.rejected
        ),
        "excluded_rows": sum(
            1 for dataset in records.values() for r in dataset or [] if r.excluded
        ),
        "warning_rows": sum(
            1
            for dataset in records.values()
            for r in dataset or []
            if r.accepted and any(i.severity == WARNING for i in r.issues)
        ),
        "issues": len(issues),
    }


def dataset_counts(records):
    """
    counts row outcomes per dataset
    :param records: mapping of dataset role to canonical records
    :returns: mapping of dataset role to counts
    """
    counts = {}
    for dataset in DATASET_ORDER:
        dataset_records = records.get(dataset) or []
        counts[dataset] = {
            "rows": len(dataset_records),
            "accepted": sum(1 for r in dataset_records if r.accepted),
            "rejected": sum(1 for r in dataset_records if r.rejected),
            "excluded": sum(1 for r in dataset_records if r.excluded),
            "accepted_with_warnings": sum(
                1
                for r in dataset_records
                if r.accepted and any(i.severity == WARNING for i in r.issues)
            ),
        }
    return counts


def all_issues(records):
    """
    gathers every issue in a deterministic order
    :param records: mapping of dataset role to canonical records
    :returns: sorted list of issues
    """
    issues = [
        issue
        for dataset in records.values()
        for record in dataset or []
        for issue in record.issues
    ]
    return sorted(issues, key=lambda issue: issue.sort_key())


def process(profile, input_dir):
    """
    runs exports through profile mapping, validation, and reconciliation
    :param profile: validated import profile
    :param input_dir: directory containing the exports
    :returns: run result
    """
    input_dir = Path(input_dir)
    discovered, ignored = discover_inputs(input_dir, profile)

    inputs = []
    records = {}
    for role in DATASET_ORDER:
        if role not in profile.datasets:
            continue
        spec = profile.datasets[role]
        role_records = []
        for path in discovered[role]:
            table = read_table(path, spec, profile)
            inputs.append(
                InputFile(
                    role,
                    path.name,
                    table.sha256,
                    len(table.rows) + len(table.malformed_rows),
                )
            )
            role_records.extend(canonicalize(table, spec, profile))
        records[role] = role_records if discovered[role] else None

    if records.get("customers") is None:
        records.pop("customers", None)

    validate_records(records, profile)

    customers, orders, payments = build_frames(records, profile)
    if orders.empty:
        ledger = pd.DataFrame(columns=LEDGER_COLUMNS)
        reconciled_at = datetime.now(timezone.utc)
    else:
        report = build_report(customers, orders, payments)
        reconciled_at = report["reconciliation_timestamp"].iloc[0]
        ledger = build_ledger(records, report, profile)
    verify_integrity(ledger, records)

    return RunResult(
        profile=profile,
        input_dir=input_dir,
        inputs=inputs,
        ignored_files=ignored,
        records=records,
        ledger=ledger,
        summary=summarize(ledger, records),
        counts=dataset_counts(records),
        reconciled_at=reconciled_at,
        issues=all_issues(records),
    )


def severity_counts(issues):
    """
    counts issues by severity
    :param issues: list of issues
    :returns: mapping of severity to count
    """
    counts = Counter(issue.severity for issue in issues)
    return {
        severity: counts.get(severity, 0) for severity in (ERROR, WARNING, EXCLUDED)
    }
