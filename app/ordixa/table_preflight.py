"""
read-only preflight for clean and compare profiles

the table counterpart of the reconciliation preflight: it checks one export
(or the two exports of a comparison) against a profile, processes them in
memory with the real cleaning and comparison code, and reports every
structural problem and normalization risk at once. nothing is written and no
cell values are reported: findings name files, columns, issue codes, and
counts only. a clean preflight is not proof that the data is complete or
correct
"""

import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

from app.ordixa.inspection import inspect_file
from app.ordixa.issues import InputError
from app.ordixa.preflight import (
    BLOCKING,
    HIGH_REJECTION_SHARE,
    LEVEL_ORDER,
    NOTE,
    PROHIBITED_HEADER,
    REVIEW,
    check_file,
    finding,
    looks_personal,
    table_header,
)
from app.ordixa.tabular import (
    INCOMPLETE,
    REJECTED,
    TabularIntegrityError,
    clean_table,
    compare_tables,
    token_is_value,
)

# rejections about relationships between rows rather than how a value is written
RELATIONSHIP_CODES = frozenset({"conflicting_key", "key_on_rejected_row"})
# an unambiguous probe: day 3 of month 4 reads differently if day and month swap
DATE_PROBE = datetime(2031, 4, 3, 14, 5, 9)


def ambiguous_date_formats(formats):
    """
    finds pairs of declared date formats that read the same text differently
    :param formats: declared strptime formats
    :returns: list of (format, format) pairs
    """
    pairs = []
    for index, first in enumerate(formats):
        text = DATE_PROBE.strftime(first)
        for second in formats[index + 1 :]:
            try:
                parsed = datetime.strptime(text, second)
            except ValueError:
                continue
            if parsed.date() != DATE_PROBE.date():
                pairs.append((first, second))
    return pairs


def profile_findings(profile, comparing):
    """
    reports normalization risks visible from the profile alone
    :param profile: table profile
    :param comparing: true when two exports are being compared
    :returns: list of findings
    """
    findings = []
    for token in sorted(profile.blank_values):
        typed = [
            column.name
            for column in profile.columns
            if token_is_value(token, column, profile)
        ]
        if typed:
            findings.append(
                finding(
                    REVIEW,
                    "blank_token_is_a_value",
                    f"blank token {token!r} is also a valid value of "
                    f"{', '.join(typed)}; real values written that way will be "
                    "treated as blank (and compare equal to an empty cell)",
                )
            )
    for first, second in ambiguous_date_formats(profile.date_formats):
        findings.append(
            finding(
                REVIEW,
                "ambiguous_date_formats",
                f"date formats {first!r} and {second!r} can read the same text as "
                "different dates; such values will be rejected as ambiguous",
            )
        )
    for name in profile.key:
        if profile.column(name).type == "text":
            findings.append(
                finding(
                    NOTE,
                    "text_key",
                    f"key column {name} is text: keys match exactly, including "
                    "case, inner spacing, and Unicode form; use identifier for codes",
                )
            )
    if profile.kind == "compare" and profile.ignore:
        findings.append(
            finding(
                REVIEW,
                "ignored_columns",
                f"the profile never compares {', '.join(profile.ignore)}; changes "
                "in those columns are not reported",
            )
        )
    if profile.kind == "compare" and not comparing:
        findings.append(
            finding(
                NOTE,
                "single_input",
                "one file was checked; pass --before and --after to preview the "
                "comparison itself",
            )
        )
    return findings


def header_findings(result, profile):
    """
    reports mapped columns whose headers suggest sensitive data
    :param result: clean result
    :param profile: table profile
    :returns: list of findings
    """
    findings = []
    name = result.input.name
    for column in profile.columns:
        if column.source not in result.header:
            continue
        if PROHIBITED_HEADER.search(column.source):
            findings.append(
                finding(
                    BLOCKING,
                    "prohibited_column",
                    f"{name} column {column.source!r} looks like payment, bank, "
                    "government ID, or credential data and is mapped, so outputs "
                    "would contain it; remove it from the profile and follow "
                    "'Unexpected personal data' in docs/DATA_HANDLING.md",
                )
            )
        elif looks_personal(column.source):
            findings.append(
                finding(
                    NOTE,
                    "mapped_personal_column",
                    f"{name} column {column.source!r} may hold personal data; it is "
                    f"mapped to {column.name}, so outputs will contain it",
                )
            )
    return findings


def decomposed_text(result, profile):
    """
    counts accepted text values not in composed (NFC) Unicode form, by column
    :param result: clean result
    :param profile: table profile
    :returns: counter of column name to value count
    """
    counts = Counter()
    for record in result.records:
        for column in profile.columns:
            value = record.values[column.name]
            if isinstance(value, str) and not unicodedata.is_normalized("NFC", value):
                counts[column.name] += 1
    return counts


def row_findings(result, profile, comparing):
    """
    reports row-level risks found while cleaning one export in memory
    :param result: clean result
    :param profile: table profile
    :param comparing: true when the comparison assessment covers missing columns
    :returns: list of findings
    """
    name = result.input.name
    counts = result.counts()
    findings = []
    if not comparing:
        for column_name in result.missing_columns:
            column = profile.column(column_name)
            findings.append(
                finding(
                    REVIEW,
                    "optional_column_missing",
                    f"{name} has no {column.source!r} column; {column_name} will be "
                    "blank in every row",
                )
            )
    if counts["rows_read"] == 0:
        findings.append(
            finding(REVIEW, "no_rows", f"{name} has a header but no data rows")
        )
        return findings

    unparsed = len(
        {
            issue.row
            for issue in result.issues
            if issue.outcome == REJECTED and issue.code not in RELATIONSHIP_CODES
        }
    )
    if unparsed / counts["rows_read"] > HIGH_REJECTION_SHARE:
        findings.append(
            finding(
                REVIEW,
                "high_rejection_rate",
                f"{unparsed} of {counts['rows_read']} rows in {name} have values the "
                "profile cannot read; check that its column mapping, date, amount, "
                "and identifier rules match this export",
            )
        )

    in_key = Counter()
    for (column_name, _), count in result.blank_hits.items():
        if column_name in profile.key:
            in_key[column_name] += count
    for column_name, count in sorted(in_key.items()):
        findings.append(
            finding(
                REVIEW,
                "blank_token_in_key",
                f"{count} row(s) in {name} hold a blank token in key column "
                f"{column_name} and will be rejected for a missing key",
            )
        )
    for column_name, count in sorted(decomposed_text(result, profile).items()):
        findings.append(
            finding(
                REVIEW,
                "decomposed_unicode",
                f"{count} value(s) in {column_name} of {name} use decomposed "
                "Unicode (such as an accent stored as a separate mark); they will "
                "not match the composed spelling of the same text",
            )
        )
    return findings


def issue_summary(result):
    """
    counts row issues by outcome, code, and column, without values
    :param result: clean result
    :returns: list of dictionaries
    """
    counts = Counter((i.outcome, i.code, i.column) for i in result.issues if i.row)
    return [
        {"outcome": outcome, "code": code, "column": column, "rows": rows}
        for (outcome, code, column), rows in sorted(counts.items())
    ]


def read_headers(profile, inputs):
    """
    reads the header of each file being checked, for the explanation
    :param profile: table profile
    :param inputs: (role, path) pairs
    :returns: {role: header tuple}, empty for a file that cannot be read
    """
    headers = {}
    for role, path in inputs:
        path = Path(path)
        header = None
        if path.is_file():
            report = inspect_file(path, profile.csv_encoding, max_rows=1)
            if not report["errors"]:
                header = table_header(report, profile.read_spec(role))
        headers[role] = tuple(header or ())
    return headers


def table_preflight(profile, inputs):
    """
    checks one export, or a before/after pair, against a table profile

    nothing is written; the exports are only read
    :param profile: validated table profile
    :param inputs: list of (role, path) pairs: [("input", p)] or
        [("before", p1), ("after", p2)]
    :returns: preflight report dictionary
    """
    comparing = [role for role, _ in inputs] == ["before", "after"]
    findings = profile_findings(profile, comparing)
    entries = []
    results = {}

    for role, path in inputs:
        path = Path(path)
        entry = {"role": role, "file": path.name, "counts": None, "issues": []}
        entries.append(entry)
        if not path.is_file():
            findings.append(
                finding(BLOCKING, "input_error", f"{role} file not found: {path}")
            )
            continue
        entry["bytes"] = path.stat().st_size
        suffix = path.suffix.lower().lstrip(".")
        if suffix not in profile.formats:
            findings.append(
                finding(
                    BLOCKING,
                    "unsupported_format",
                    f"{path.name} is not one of the profile's accepted formats "
                    f"{sorted(profile.formats)}",
                )
            )
            continue

        file_findings = []
        check_file(path, profile.read_spec(role), profile, file_findings)
        findings += file_findings
        if any(item["level"] == BLOCKING for item in file_findings):
            continue
        try:
            result = clean_table(profile, path, role)
        except (InputError, TabularIntegrityError) as error:
            findings.append(finding(BLOCKING, "input_error", str(error)))
            continue
        results[role] = result
        entry["counts"] = result.counts()
        entry["issues"] = issue_summary(result)
        findings += header_findings(result, profile)
        findings += row_findings(result, profile, comparing)

    comparison = assessment = None
    blocked = any(item["level"] == BLOCKING for item in findings)
    if comparing and not blocked:
        try:
            compared = compare_tables(profile, inputs[0][1], inputs[1][1])
        except (InputError, TabularIntegrityError) as error:
            findings.append(finding(BLOCKING, "input_error", str(error)))
        else:
            comparison = compared.counts()
            assessment = compared.assessment()
            for item in assessment["findings"]:
                level = REVIEW if item["level"] in (INCOMPLETE, "warning") else NOTE
                findings.append(finding(level, item["code"], item["message"]))

    return build_report(profile, entries, findings, comparison, assessment)


def build_report(profile, entries, findings, comparison, assessment):
    """
    assembles the table preflight report and its overall readiness
    :param profile: table profile
    :param entries: per-input summaries
    :param findings: collected findings
    :param comparison: comparison counts, or none
    :param assessment: comparison assessment, or none
    :returns: report dictionary
    """
    findings = sorted(findings, key=lambda item: LEVEL_ORDER[item["level"]])
    levels = {item["level"] for item in findings}
    rejected = any(
        entry["counts"] and entry["counts"]["rows_rejected"] for entry in entries
    )
    if BLOCKING in levels:
        readiness = "blocked"
    elif REVIEW in levels or rejected:
        readiness = "review"
    else:
        readiness = "ready"
    return {
        "profile": {
            "name": profile.name,
            "version": profile.version,
            "kind": profile.kind,
        },
        "key": list(profile.key),
        "readiness": readiness,
        "inputs": entries,
        "comparison": comparison,
        "assessment": assessment,
        "findings": findings,
    }


READINESS_TEXT = {
    "blocked": "BLOCKED: resolve the blocking findings, then check again",
    "review": "REVIEW: the files can be processed; review the warnings first",
    "ready": "READY: no structural problems found",
}
ASSESSMENT_LABELS = {
    "complete": "complete",
    "complete_with_warnings": "complete with warnings",
    "incomplete": "INCOMPLETE",
}


def format_counts(counts):
    """
    renders one input's row outcome counts
    :param counts: clean counts
    :returns: text
    """
    return (
        f"{counts['rows_read']} rows read: {counts['rows_written']} accepted, "
        f"{counts['rows_rejected']} rejected, {counts['duplicate_rows_removed']} "
        f"exact duplicate(s) removed, {counts['conflicting_keys']} conflicting "
        "key(s)"
    )


def format_table_preflight(report):
    """
    renders a table preflight report as plain text without cell values
    :param report: preflight report dictionary
    :returns: text
    """
    profile = report["profile"]
    files = ", ".join(entry["file"] for entry in report["inputs"])
    lines = [
        f"Preflight of {files} against {profile['name']} {profile['version']} "
        f"({profile['kind']}; read-only; nothing is written)",
        f"  business key: {', '.join(report['key']) or 'none'}",
        "",
        "Inputs (processed in memory)",
    ]
    for entry in report["inputs"]:
        counts = entry["counts"]
        summary = format_counts(counts) if counts else "not processed"
        lines.append(f"  {entry['role']:<6} {entry['file']}: {summary}")
        for item in entry["issues"]:
            column = f" ({item['column']})" if item["column"] else ""
            lines.append(
                f"    {item['outcome'].lower():<17} {item['code']}{column}: "
                f"{item['rows']} row(s)"
            )

    comparison = report["comparison"]
    if comparison is not None:
        lines += [
            "",
            "Comparison (processed in memory)",
            f"  {comparison['added']} added, {comparison['removed']} removed, "
            f"{comparison['modified']} modified, {comparison['unchanged']} unchanged",
            f"  {comparison['ambiguous_keys']} ambiguous key(s), "
            f"{comparison['invalid_keys']} invalid key(s), "
            f"{comparison['unkeyed_rejected_rows']} rejected row(s) without a key",
            f"  result: {ASSESSMENT_LABELS[report['assessment']['level']]}",
        ]

    lines += ["", "Findings"]
    if not report["findings"]:
        lines.append("  none")
    for item in report["findings"]:
        lines.append(f"  {item['level'].upper():<8} {item['code']}: {item['message']}")
    lines += [
        "",
        f"Readiness: {READINESS_TEXT[report['readiness']]}",
        "A preflight result is not proof that the data is complete or correct; "
        "review the outputs after the run.",
    ]
    return "\n".join(lines)
