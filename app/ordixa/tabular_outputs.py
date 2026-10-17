"""
run directories for the clean and compare workflows

runs are published through the same staging-then-rename path as
reconciliation runs and verified by the same verify command; manifests
carry an explicit workflow name and version so they are never mistaken for
reconciliation manifests (which have no workflow field)
"""

import hashlib
import json
from datetime import datetime, timezone

from app.ordixa.change_report import issue_rows, write_change_report
from app.ordixa.manifest import (
    MANIFEST_VERSION,
    code_version,
    describe_version,
    output_entries,
    plain,
    publish_run,
    write_csv,
    write_manifest,
)
from app.ordixa.tabular import OUTCOMES, REJECTED, as_text
from app.ordixa.tabular_profile import WORKFLOW_VERSION

CLEANED_NAME = "cleaned_data.csv"
CLEAN_ISSUES_NAME = "cleaning_issues.csv"
REPORT_NAME = "comparison_report.xlsx"
ADDED_NAME = "added_records.csv"
REMOVED_NAME = "removed_records.csv"
MODIFIED_NAME = "modified_values.csv"
COMPARE_ISSUES_NAME = "comparison_issues.csv"
ISSUE_COLUMNS = [
    "role",
    "file",
    "row",
    "outcome",
    "code",
    "key",
    "column",
    "source_column",
    "value",
    "message",
]


def record_rows(profile, records):
    """
    converts cleaned records into CSV rows of canonical text
    :param profile: table profile
    :param records: records to convert
    :returns: list of dictionaries keyed by output column
    """
    return [
        {column.name: as_text(record.values[column.name]) for column in profile.columns}
        for record in records
    ]


def issue_csv_rows(issues):
    """
    converts issues into CSV rows, adding the source column name
    :param issues: list of table issues
    :returns: list of dictionaries keyed by ISSUE_COLUMNS
    """
    return [
        {**row, "source_column": issue.source_column}
        for row, issue in zip(issue_rows(issues), issues)
    ]


def change_rows(result):
    """
    converts value changes into CSV rows
    :param result: compare result
    :returns: list of dictionaries
    """
    return [
        {
            **dict(zip(result.profile.key, change.key)),
            "column": change.column,
            "before": as_text(change.before),
            "after": as_text(change.after),
            "difference": as_text(change.difference),
        }
        for change in result.changes
    ]


def outcome_counts(issues):
    """
    counts issues by outcome
    :param issues: list of table issues
    :returns: dictionary with every outcome
    """
    return {
        outcome: sum(1 for issue in issues if issue.outcome == outcome)
        for outcome in OUTCOMES
    }


def fingerprint(workflow, payload):
    """
    hashes the logical result of a run, independent of time and directory
    :param workflow: clean or compare
    :param payload: rows, issues, and counts that make up the result
    :returns: SHA-256 hex digest
    """
    document = {
        "workflow": workflow,
        "workflow_version": WORKFLOW_VERSION,
        **plain(payload),
    }
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def base_result(workflow, profile, inputs, issues, version):
    """
    builds the manifest fields shared by both workflows
    :param workflow: clean or compare
    :param profile: table profile
    :param inputs: input files read
    :param issues: every issue found
    :param version: code version dictionary
    :returns: dictionary
    """
    rejected = any(issue.outcome == REJECTED for issue in issues)
    return {
        "workflow": workflow,
        "workflow_version": WORKFLOW_VERSION,
        "status": "completed_with_rejections" if rejected else "completed",
        "profile": {
            "name": profile.name,
            "version": profile.version,
            "kind": profile.kind,
            "sha256": profile.sha256,
            "key": list(profile.key),
        },
        "code_version": version,
        "inputs": [
            {
                "role": item.role,
                "file": item.name,
                "sha256": item.sha256,
                "data_rows": item.data_rows,
            }
            for item in inputs
        ],
        "issue_counts": outcome_counts(issues),
    }


def execution(run_id, started_at, final_name):
    """
    builds the run-specific manifest section
    :param run_id: run identifier
    :param started_at: UTC start time
    :param final_name: published directory name
    :returns: dictionary
    """
    return {
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "output_directory": final_name,
    }


def write_clean_run(result, out_dir, started_at=None):
    """
    writes cleaned_data.csv, cleaning_issues.csv, and manifest.json
    :param result: clean result
    :param out_dir: parent output directory
    :param started_at: optional UTC start time
    :returns: tuple of run directory and manifest dictionary
    """
    started_at = started_at or datetime.now(timezone.utc)
    profile = result.profile
    rows = record_rows(profile, result.records)
    issues = issue_csv_rows(result.issues)
    columns = [column.name for column in profile.columns]

    def write(run_dir, final_name, run_id):
        write_csv(run_dir / CLEANED_NAME, columns, rows)
        write_csv(run_dir / CLEAN_ISSUES_NAME, ISSUE_COLUMNS, issues)
        manifest = {
            "manifest_version": MANIFEST_VERSION,
            "result": {
                **base_result(
                    "clean", profile, result.inputs, result.issues, code_version()
                ),
                "row_counts": result.counts(),
                "artifact_rows": {
                    CLEANED_NAME: len(rows),
                    CLEAN_ISSUES_NAME: len(issues),
                },
                "result_fingerprint": fingerprint(
                    "clean",
                    {"rows": rows, "issues": issues, "counts": result.counts()},
                ),
            },
            "execution": execution(run_id, started_at, final_name),
            "outputs": output_entries(
                run_dir, ((CLEANED_NAME, True), (CLEAN_ISSUES_NAME, True))
            ),
        }
        write_manifest(run_dir, manifest)
        return manifest

    return publish_run(out_dir, started_at, write)


def write_compare_run(result, out_dir, started_at=None):
    """
    writes the change report workbook, CSV artifacts, and manifest.json
    :param result: compare result
    :param out_dir: parent output directory
    :param started_at: optional UTC start time
    :returns: tuple of run directory and manifest dictionary
    """
    started_at = started_at or datetime.now(timezone.utc)
    profile = result.profile
    columns = [column.name for column in profile.columns]
    added = record_rows(profile, result.added)
    removed = record_rows(profile, result.removed)
    changes = change_rows(result)
    issues = issue_csv_rows(result.issues)
    counts = result.counts()
    version = code_version()
    shared = base_result("compare", profile, result.inputs, result.issues, version)

    def write(run_dir, final_name, run_id):
        write_change_report(
            result,
            run_dir / REPORT_NAME,
            {
                "run_id": run_id,
                "generated_at": started_at.strftime("%Y-%m-%d %H:%M:%S"),
                "code_version": describe_version(version),
                "status": shared["status"].replace("_", " "),
            },
        )
        write_csv(run_dir / ADDED_NAME, columns, added)
        write_csv(run_dir / REMOVED_NAME, columns, removed)
        write_csv(
            run_dir / MODIFIED_NAME,
            [*profile.key, "column", "before", "after", "difference"],
            changes,
        )
        write_csv(run_dir / COMPARE_ISSUES_NAME, ISSUE_COLUMNS, issues)
        manifest = {
            "manifest_version": MANIFEST_VERSION,
            "result": {
                **shared,
                "compared_columns": result.compared_columns,
                "ignored_columns": list(profile.ignore),
                "row_counts": {
                    "before": result.before.counts(),
                    "after": result.after.counts(),
                },
                "comparison": counts,
                "artifact_rows": {
                    ADDED_NAME: len(added),
                    REMOVED_NAME: len(removed),
                    MODIFIED_NAME: len(changes),
                    COMPARE_ISSUES_NAME: len(issues),
                },
                "result_fingerprint": fingerprint(
                    "compare",
                    {
                        "status": [
                            [list(key), kind] for key, kind in result.status.items()
                        ],
                        "added": added,
                        "removed": removed,
                        "changes": changes,
                        "issues": issues,
                        "counts": counts,
                    },
                ),
            },
            "execution": execution(run_id, started_at, final_name),
            "outputs": output_entries(
                run_dir,
                (
                    (ADDED_NAME, True),
                    (REMOVED_NAME, True),
                    (MODIFIED_NAME, True),
                    (COMPARE_ISSUES_NAME, True),
                    (REPORT_NAME, False),
                ),
            ),
        }
        write_manifest(run_dir, manifest)
        return manifest

    return publish_run(out_dir, started_at, write)
