"""
pilot preflight: checks a batch of exports against a profile before a real run

it combines the existing discovery, header, and processing code so an operator
sees every structural problem at once instead of one failed run at a time.
nothing is written and no cell values are reported: findings name files,
columns, issue codes, and counts only. a clean preflight is not proof that the
data is complete or correct
"""

import re
from collections import Counter
from pathlib import Path

from app.ordixa.adapters import MAX_INPUT_BYTES, match_inputs, missing_columns
from app.ordixa.inspection import UNSUPPORTED_SUFFIXES, inspect_file
from app.ordixa.issues import ERROR, EXCLUDED, WARNING, InputError
from app.ordixa.pipeline import DATASET_ORDER, ReconciliationIntegrityError, process

BLOCKING = "blocking"
REVIEW = "warning"
NOTE = "note"
LEVEL_ORDER = {BLOCKING: 0, REVIEW: 1, NOTE: 2}

# share of a dataset's rows failing to parse above which the profile is suspect
HIGH_REJECTION_SHARE = 0.2
# rejections about relationships between rows rather than how a value is written
RELATIONSHIP_CODES = frozenset(
    {
        "conflicting_duplicate_id",
        "customer_not_found",
        "customer_rejected",
        "duplicate_row",
        "identifier_collision",
        "order_not_in_run",
        "order_rejected",
    }
)

# headers that should never arrive: the customer must re-export without them
PROHIBITED_HEADER = re.compile(
    r"card ?(number|no\b|num)|\bpan\b|\bcvv|\bcvc|security code|\biban\b|"
    r"account ?(number|no\b|num)|routing|sort code|\bssn\b|social security|"
    r"tax ?id|\btin\b|\bein\b|passport|driver|licen[cs]e|birth|\bdob\b|password",
    re.IGNORECASE,
)
# headers that usually hold personal data; fine if mapped, avoidable if not
PERSONAL_HEADER = re.compile(
    r"address|street|city|postal|\bzip|e-?mail|phone|mobile|name|note|comment|"
    r"tag|marketing|consent|\bip\b|device|gender",
    re.IGNORECASE,
)
# names of things rather than people, such as Product Name or Supplier Name
BUSINESS_NAME_HEADER = re.compile(
    r"^(product|item|sku|category|company|business|store|shop|brand|supplier|"
    r"vendor|warehouse|location|department|plan)[ _-]?(name|title)$",
    re.IGNORECASE,
)


def looks_personal(header):
    """
    applies the personal-data header heuristic, skipping names of things
    :param header: source column name
    :returns: true when the header suggests personal data
    """
    return bool(PERSONAL_HEADER.search(header)) and not BUSINESS_NAME_HEADER.match(
        header.strip()
    )


def finding(level, code, message):
    """
    builds one preflight finding
    :param level: blocking, warning, or note
    :param code: stable machine-readable code
    :param message: explanation naming files and columns, never cell values
    :returns: finding dictionary
    """
    return {"level": level, "code": code, "message": message}


def table_header(report, spec):
    """
    selects the header a dataset would read from an inspected file
    :param report: inspection report for one file
    :param spec: dataset specification
    :returns: list of header names, or none when the table is absent
    """
    tables = report["tables"]
    if not tables:
        return None
    if spec.sheet is not None:
        tables = [table for table in tables if table["name"] == spec.sheet]
        if not tables:
            return None
    return [column["name"] for column in tables[0]["columns"]]


def check_file(path, spec, profile, findings):
    """
    checks one discovered file's size, readability, and header
    :param path: input file path
    :param spec: dataset specification
    :param profile: validated import profile
    :param findings: list collecting findings
    :returns: file summary dictionary
    """
    summary = {"file": path.name, "bytes": path.stat().st_size, "unused_columns": []}
    if summary["bytes"] > MAX_INPUT_BYTES:
        findings.append(
            finding(
                BLOCKING,
                "file_too_large",
                f"{path.name} is above the {MAX_INPUT_BYTES // (1024 * 1024)} MB "
                "input limit; ask for the export split by reporting period",
            )
        )
        return summary

    report = inspect_file(path, profile.csv_encoding, max_rows=1)
    for error in report["errors"]:
        findings.append(finding(BLOCKING, "unreadable_file", f"{path.name}: {error}"))
    header = None if report["errors"] else table_header(report, spec)
    if header is None:
        if not report["errors"]:
            findings.append(
                finding(
                    BLOCKING,
                    "missing_worksheet",
                    f"{path.name} has no worksheet named {spec.sheet!r}",
                )
            )
        return summary

    duplicates = sorted({name for name in header if name and header.count(name) > 1})
    if duplicates:
        findings.append(
            finding(
                BLOCKING,
                "duplicate_header",
                f"{path.name} has duplicate column headers: {duplicates}",
            )
        )
    missing = missing_columns(tuple(header), spec)
    if missing:
        findings.append(
            finding(
                BLOCKING,
                "missing_column",
                f"{path.name} ({spec.role}) is missing required columns: "
                f"{', '.join(missing)}; confirm with the customer what changed "
                "before editing the profile",
            )
        )

    mapped = set(spec.source_columns())
    for name in header:
        if not name or name in mapped:
            continue
        summary["unused_columns"].append(name)
        if PROHIBITED_HEADER.search(name):
            findings.append(
                finding(
                    BLOCKING,
                    "prohibited_column",
                    f"{path.name} column {name!r} looks like payment, bank, "
                    "government ID, or credential data; stop and follow "
                    "'Unexpected personal data' in docs/DATA_HANDLING.md",
                )
            )
        elif looks_personal(name):
            findings.append(
                finding(
                    REVIEW,
                    "unused_personal_column",
                    f"{path.name} column {name!r} is not used by the profile and "
                    "may hold personal data; ask the customer to leave it out",
                )
            )
    others = [
        name
        for name in summary["unused_columns"]
        if not PROHIBITED_HEADER.search(name) and not looks_personal(name)
    ]
    if others:
        findings.append(
            finding(
                NOTE,
                "unused_column",
                f"{path.name} has {len(others)} column(s) the profile does not use: "
                f"{others}; they can be left out of future exports",
            )
        )
    return summary


def directory_findings(input_dir, ignored, findings):
    """
    reports files in the batch that no dataset will read
    :param input_dir: export directory
    :param ignored: names of files matching no dataset
    :param findings: list collecting findings
    :returns: none
    """
    for name in ignored:
        if name.startswith("."):
            continue
        reason = UNSUPPORTED_SUFFIXES.get(Path(name).suffix.lower())
        if reason:
            findings.append(finding(REVIEW, "unsupported_file", f"{name}: {reason}"))
        else:
            findings.append(
                finding(
                    REVIEW,
                    "ignored_file",
                    f"{name} matches no dataset in the profile and will not be "
                    "read; confirm it is not a renamed export",
                )
            )


def currency_findings(profile, findings):
    """
    states the currency assumption the run will make
    :param profile: validated import profile
    :param findings: list collecting findings
    :returns: none
    """
    currency = profile.amounts.currency
    for role in ("orders", "payments"):
        spec = profile.datasets.get(role)
        if spec is not None and "currency" not in spec.columns:
            findings.append(
                finding(
                    NOTE,
                    "currency_assumed",
                    f"{role} have no currency column mapped; every amount is "
                    f"assumed to be {currency}",
                )
            )


def row_checks(profile, input_dir, findings):
    """
    processes the batch in memory and summarizes row outcomes without values
    :param profile: validated import profile
    :param input_dir: export directory
    :param findings: list collecting findings
    :returns: row summary dictionary, or none when processing stopped
    """
    try:
        result = process(profile, input_dir)
    except InputError as error:
        findings.append(finding(BLOCKING, "input_error", str(error)))
        return None
    except ReconciliationIntegrityError as error:
        findings.append(
            finding(
                BLOCKING,
                "integrity_check_failed",
                f"reconciled totals failed the independent cross-check: {error}",
            )
        )
        return None

    issue_counts = Counter(
        (issue.dataset, issue.severity, issue.code, issue.field)
        for issue in result.issues
    )
    issues = [
        {
            "dataset": dataset,
            "severity": severity,
            "code": code,
            "field": field_name,
            "rows": count,
        }
        for (dataset, severity, code, field_name), count in sorted(
            issue_counts.items(),
            key=lambda item: (
                DATASET_ORDER.index(item[0][0]),
                (ERROR, WARNING, EXCLUDED).index(item[0][1]),
                item[0][2],
                item[0][3],
            ),
        )
    ]

    for dataset, counts in result.counts.items():
        if dataset not in result.records:
            continue
        if counts["rows"] == 0:
            findings.append(
                finding(
                    BLOCKING if dataset == "orders" else REVIEW,
                    "no_rows",
                    f"the {dataset} files have a header but no data rows",
                )
            )
            continue
        unparsed = sum(
            1
            for record in result.records[dataset]
            if any(
                issue.severity == ERROR and issue.code not in RELATIONSHIP_CODES
                for issue in record.issues
            )
        )
        if unparsed / counts["rows"] > HIGH_REJECTION_SHARE:
            findings.append(
                finding(
                    REVIEW,
                    "high_rejection_rate",
                    f"{unparsed} of {counts['rows']} {dataset} rows have values the "
                    "profile cannot read; check that its date, amount, identifier, "
                    "and status rules match this export",
                )
            )

    unmatched = sum(
        item["rows"] for item in issues if item["code"] == "order_not_in_run"
    )
    if unmatched:
        findings.append(
            finding(
                REVIEW,
                "order_not_in_run",
                f"{unmatched} payment row(s) reference an order that is not in this "
                "batch and will be rejected; Ordixa never matches across runs or by "
                "amount, so confirm each reference with the customer",
            )
        )
    currency_rows = sum(
        item["rows"]
        for item in issues
        if item["code"] in ("currency_mismatch", "missing_currency")
    )
    if currency_rows:
        findings.append(
            finding(
                REVIEW,
                "currency_rows",
                f"{currency_rows} row(s) have a blank currency or one other than "
                f"{profile.amounts.currency}; amounts are never converted",
            )
        )

    return {
        "counts": {
            dataset: counts
            for dataset, counts in result.counts.items()
            if dataset in result.records
        },
        "issues": issues,
        "orders": result.summary["orders"],
        "status_counts": result.summary["status_counts"],
    }


def preflight(profile, input_dir):
    """
    checks an export batch against a profile without writing anything
    :param profile: validated import profile
    :param input_dir: directory containing the exports
    :returns: preflight report dictionary
    """
    input_dir = Path(input_dir)
    findings = []
    datasets = {}

    try:
        discovered, ignored, problems = match_inputs(input_dir, profile)
    except InputError as error:
        findings.append(finding(BLOCKING, "input_error", str(error)))
        return build_report(profile, input_dir, datasets, findings, None)

    for problem in problems:
        code = "missing_dataset" if problem.startswith("no ") else "ambiguous_file"
        findings.append(finding(BLOCKING, code, problem))

    for role in DATASET_ORDER:
        spec = profile.datasets.get(role)
        if spec is None:
            continue
        datasets[role] = {
            "required": spec.required,
            "patterns": list(spec.files),
            "files": [
                check_file(path, spec, profile, findings) for path in discovered[role]
            ],
        }
        if not discovered[role] and not spec.required:
            findings.append(
                finding(
                    NOTE,
                    "optional_dataset_absent",
                    f"no {role} file supplied; orders are reconciled without it",
                )
            )

    directory_findings(input_dir, ignored, findings)
    currency_findings(profile, findings)

    rows = None
    if not any(item["level"] == BLOCKING for item in findings):
        rows = row_checks(profile, input_dir, findings)
    return build_report(profile, input_dir, datasets, findings, rows)


def build_report(profile, input_dir, datasets, findings, rows):
    """
    assembles the preflight report and its overall readiness
    :param profile: validated import profile
    :param input_dir: export directory
    :param datasets: per-dataset file summaries
    :param findings: collected findings
    :param rows: row summary, or none when row checks did not run
    :returns: report dictionary
    """
    findings = sorted(findings, key=lambda item: LEVEL_ORDER[item["level"]])
    levels = {item["level"] for item in findings}
    if BLOCKING in levels:
        readiness = "blocked"
    elif REVIEW in levels or (
        rows and any(i["severity"] == ERROR for i in rows["issues"])
    ):
        readiness = "review"
    else:
        readiness = "ready"
    return {
        "profile": {"name": profile.name, "version": profile.version},
        "input": str(input_dir),
        "readiness": readiness,
        "datasets": datasets,
        "findings": findings,
        "rows": rows,
    }


READINESS_TEXT = {
    "blocked": "BLOCKED: resolve the blocking findings, then run preflight again",
    "review": "REVIEW: the batch can be processed; review the warnings first",
    "ready": "READY: no structural problems found",
}


def format_preflight(report):
    """
    renders a preflight report as plain text without cell values
    :param report: preflight report dictionary
    :returns: text
    """
    profile = report["profile"]
    lines = [
        f"Preflight of {report['input']} against {profile['name']} "
        f"{profile['version']} (read-only; nothing is written)",
        "",
        "Datasets",
    ]
    for role, dataset in report["datasets"].items():
        need = "required" if dataset["required"] else "optional"
        if dataset["files"]:
            files = ", ".join(
                f"{item['file']} ({item['bytes']:,} bytes)" for item in dataset["files"]
            )
        elif dataset["required"]:
            files = f"MISSING (expected {', '.join(dataset['patterns'])})"
        else:
            files = "not supplied"
        lines.append(f"  {role:<9} {need:<8} {files}")

    rows = report["rows"]
    lines += ["", "Row checks (processed in memory)"]
    if rows is None:
        lines.append("  skipped until blocking findings are resolved")
    else:
        for dataset, counts in rows["counts"].items():
            lines.append(
                f"  {dataset:<9} {counts['rows']} rows: {counts['accepted']} accepted "
                f"({counts['accepted_with_warnings']} with warnings), "
                f"{counts['rejected']} rejected, {counts['excluded']} excluded"
            )
        status = rows["status_counts"]
        lines.append(
            f"  {rows['orders']} orders would reconcile: {status['paid']} paid, "
            f"{status['partial']} partial, {status['unpaid']} unpaid, "
            f"{status['overpaid']} overpaid"
        )
        for item in rows["issues"]:
            field_name = f".{item['field']}" if item["field"] else ""
            lines.append(
                f"  {item['severity']:<8} {item['dataset']}{field_name} "
                f"{item['code']}: {item['rows']} row(s)"
            )

    lines += ["", "Findings"]
    if not report["findings"]:
        lines.append("  none")
    for item in report["findings"]:
        lines.append(f"  {item['level'].upper():<8} {item['code']}: {item['message']}")

    lines += [
        "",
        f"Readiness: {READINESS_TEXT[report['readiness']]}",
        "A preflight result is not proof that the data is complete or correct; "
        "review the workbook and verify totals independently after the run.",
    ]
    return "\n".join(lines)
