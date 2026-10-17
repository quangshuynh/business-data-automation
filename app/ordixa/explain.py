"""
plain-language explanations of how a profile will interpret an export

used by check-profile --explain so an operator can confirm the mapping and
normalization rules before trusting a run. explanations are built from the
profile alone (plus, when files are supplied, which configured headers were
found); they never contain cell values
"""

from app.ordixa.profile import SCHEMA_VERSION

TYPE_RULES = {
    "text": "trimmed text, kept exactly otherwise",
    "identifier": "exact text: case and leading zeros kept, no spaces",
    "decimal": "exact decimal amount, never floating point",
    "integer": "whole number (digits with an optional leading minus)",
    "date": "date in a declared format, written as YYYY-MM-DD",
}


def amount_summary(rules):
    """
    describes a profile's monetary parsing rules in one line
    :param rules: amount rules
    :returns: text
    """
    symbols = ", ".join(repr(symbol) for symbol in rules.currency_symbols) or "none"
    thousands = repr(rules.thousands_separator) if rules.thousands_separator else "none"
    return (
        f"{rules.currency}; symbols {symbols}; thousands {thousands}; decimal "
        f"{rules.decimal_separator!r}; at most {rules.max_decimal_places} decimal "
        f"place(s); negatives as {', '.join(sorted(rules.negative_styles))}; parsed "
        "as exact decimals and kept at cent precision"
    )


def explain_table_profile(profile, headers=None):
    """
    explains a clean/compare profile
    :param profile: validated table profile
    :param headers: optional {role: header tuple} of the files being checked
    :returns: explanation dictionary
    """
    headers = headers or {}
    columns = []
    for column in profile.columns:
        found = {role: column.source in header for role, header in headers.items()}
        columns.append(
            {
                "source": column.source,
                "output": column.name,
                "type": column.type,
                "required": column.required,
                "key": column.name in profile.key,
                "whitespace": column.whitespace,
                "compared": (
                    profile.kind == "compare"
                    and column.name not in profile.key
                    and column.name not in profile.ignore
                ),
                "found_in": found,
                "rule": TYPE_RULES[column.type],
            }
        )

    normalization = [
        "surrounding whitespace is trimmed in every column",
    ]
    collapsed = [c.name for c in profile.columns if c.whitespace == "collapse"]
    if collapsed:
        normalization.append(
            f"runs of inner whitespace collapse to one space in: {', '.join(collapsed)}"
        )
    if profile.blank_values:
        tokens = ", ".join(repr(token) for token in sorted(profile.blank_values))
        normalization.append(
            f"cells holding exactly {tokens} after trimming are treated as blank"
        )
    else:
        normalization.append("no blank tokens: only empty cells are blank")
    if profile.date_formats:
        normalization.append(
            f"dates are read with {', '.join(profile.date_formats)} only; a value "
            "matching several formats with different dates is rejected"
        )
    if profile.amounts is not None:
        normalization.append(f"amounts: {amount_summary(profile.amounts)}")
    normalization.append(
        "rows with an invalid or missing required value are rejected with a reason"
    )
    normalization.append("exact duplicate rows are removed; the first copy is kept")
    if profile.key:
        normalization.append(
            "rows sharing a business key but differing in any value are all "
            "rejected; no copy is chosen"
        )
    normalization.append(
        "text is compared exactly as written; Unicode is not re-normalized, so "
        "visually identical spellings in different Unicode forms differ"
    )

    explanation = {
        "profile": {
            "name": profile.name,
            "version": profile.version,
            "kind": profile.kind,
            "schema_version": SCHEMA_VERSION,
            "sha256": profile.sha256,
        },
        "input": {
            "formats": sorted(profile.formats),
            "csv_encoding": profile.csv_encoding,
            "sheet": profile.sheet,
        },
        "key": list(profile.key),
        "columns": columns,
        "normalization": normalization,
    }
    if profile.kind == "compare":
        explanation["comparison"] = {
            "matched_by": list(profile.key),
            "compared": [c["output"] for c in columns if c["compared"]],
            "ignored": list(profile.ignore),
            "rules": [
                "records match by business key only, never by row position",
                "blank, blank-token, and missing cells all compare as empty",
                "a column missing from either file is not compared, and the run "
                "is marked incomplete when it is missing from only one",
            ],
        }
    return explanation


def explain_reconciliation_profile(profile):
    """
    explains a reconciliation profile
    :param profile: validated reconciliation profile
    :returns: explanation dictionary
    """
    datasets = {}
    for role, spec in profile.datasets.items():
        datasets[role] = {
            "required": spec.required,
            "files": list(spec.files),
            "sheet": spec.sheet,
            "columns": [
                {
                    "field": field_name,
                    "sources": list(sources),
                    "optional": all(s in spec.optional_columns for s in sources),
                    "identifier": (
                        profile.identifier_mode(field_name)
                        if field_name.endswith("_id")
                        else None
                    ),
                    "prefix": spec.id_prefixes.get(field_name),
                }
                for field_name, sources in spec.columns.items()
            ],
            "date_formats": list(spec.date_formats),
            "value_maps": {
                name: dict(sorted(mapping.items()))
                for name, mapping in spec.value_maps.items()
            },
            "excluded_statuses": sorted(spec.excluded_statuses),
            "refund_amounts": spec.refund_amounts,
        }
    return {
        "profile": {
            "name": profile.name,
            "version": profile.version,
            "kind": "reconciliation",
            "schema_version": SCHEMA_VERSION,
            "sha256": profile.sha256,
        },
        "input": {
            "formats": sorted(profile.formats),
            "csv_encoding": profile.csv_encoding,
        },
        "identifiers": dict(sorted(profile.identifiers.items())),
        "amounts": amount_summary(profile.amounts),
        "missing_customer": profile.missing_customer,
        "datasets": datasets,
        "normalization": [
            "surrounding whitespace is trimmed; headers match exactly",
            "numeric identifiers keep digits only (leading zeros dropped); text "
            "identifiers keep case, separators, and leading zeros",
            "status and transaction-type labels are mapped only through the "
            "profile's value maps; unmapped labels reject the row",
            "orders and payments match by exact order identifier only, never by "
            "amount, date, or position",
        ],
    }


def format_table_explanation(explanation):
    """
    renders a table-profile explanation as plain text
    :param explanation: dictionary from explain_table_profile
    :returns: text
    """
    profile = explanation["profile"]
    source = explanation["input"]
    lines = [
        "How this profile reads an export",
        f"  profile   {profile['name']} {profile['version']} ({profile['kind']} "
        f"workflow, schema {profile['schema_version']})",
        f"  formats   {', '.join(source['formats'])}; CSV encoding "
        f"{source['csv_encoding']}; worksheet {source['sheet'] or 'first'}",
        f"  key       {', '.join(explanation['key']) or 'none (no key checks)'}",
        "",
        "Column mapping (source header -> output column)",
    ]
    width = max(len(repr(c["source"])) for c in explanation["columns"])
    for column in explanation["columns"]:
        flags = [column["type"], "required" if column["required"] else "optional"]
        if column["key"]:
            flags.append("key")
        if column["whitespace"] == "collapse":
            flags.append("collapse spaces")
        if explanation["profile"]["kind"] == "compare" and not column["key"]:
            flags.append("compared" if column["compared"] else "not compared")
        found = column["found_in"]
        if found:
            missing = [role for role, present in found.items() if not present]
            flags.append(f"MISSING in {', '.join(missing)}" if missing else "found")
        lines.append(
            f"  {column['source']!r:<{width}} -> {column['output']:<20} "
            f"{', '.join(flags)}"
        )
    lines += ["", "Normalization"]
    lines += [f"  - {rule}" for rule in explanation["normalization"]]
    comparison = explanation.get("comparison")
    if comparison:
        lines += [
            "",
            "Comparison",
            f"  matched by  {', '.join(comparison['matched_by'])}",
            f"  compared    {', '.join(comparison['compared']) or 'none'}",
            f"  ignored     {', '.join(comparison['ignored']) or 'none'}",
        ]
        lines += [f"  - {rule}" for rule in comparison["rules"]]
    return "\n".join(lines)


def format_reconciliation_explanation(explanation):
    """
    renders a reconciliation-profile explanation as plain text
    :param explanation: dictionary from explain_reconciliation_profile
    :returns: text
    """
    profile = explanation["profile"]
    lines = [
        "How this profile reads an export batch",
        f"  profile      {profile['name']} {profile['version']} (reconciliation, "
        f"schema {profile['schema_version']})",
        f"  formats      {', '.join(explanation['input']['formats'])}; CSV "
        f"encoding {explanation['input']['csv_encoding']}",
        f"  amounts      {explanation['amounts']}",
        "  identifiers  "
        + ", ".join(
            f"{name} {mode}" for name, mode in explanation["identifiers"].items()
        ),
        f"  missing customer  {explanation['missing_customer']}",
    ]
    for role, dataset in explanation["datasets"].items():
        need = "required" if dataset["required"] else "optional"
        lines += [
            "",
            f"{role} ({need}; files {', '.join(dataset['files'])}"
            + (f"; worksheet {dataset['sheet']}" if dataset["sheet"] else "")
            + ")",
        ]
        for column in dataset["columns"]:
            sources = " + ".join(repr(source) for source in column["sources"])
            notes = []
            if column["optional"]:
                notes.append("optional")
            if column["identifier"]:
                notes.append(f"{column['identifier']} identifier")
            if column["prefix"]:
                notes.append(f"prefix {column['prefix']!r} removed")
            suffix = f"  ({', '.join(notes)})" if notes else ""
            lines.append(f"  {sources} -> {column['field']}{suffix}")
        if dataset["date_formats"]:
            lines.append(f"  dates: {', '.join(dataset['date_formats'])}")
        for name, mapping in dataset["value_maps"].items():
            pairs = ", ".join(f"{label!r}={value}" for label, value in mapping.items())
            lines.append(f"  {name} labels: {pairs}")
        if dataset["excluded_statuses"]:
            lines.append(
                "  excluded (moved no money): "
                + ", ".join(repr(s) for s in dataset["excluded_statuses"])
            )
        if role == "payments":
            lines.append(f"  refund amounts are written as {dataset['refund_amounts']}")
    lines += ["", "Normalization"]
    lines += [f"  - {rule}" for rule in explanation["normalization"]]
    return "\n".join(lines)
