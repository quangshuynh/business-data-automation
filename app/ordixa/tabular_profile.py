"""
versioned TOML profiles for the spreadsheet clean and compare workflows

these profiles describe one table (an inventory list, a price list) rather
than the order, payment, and customer datasets of a reconciliation profile;
they reuse the same TOML conventions and validation helpers, and the two
profile kinds reject each other so neither can be run by the wrong command
"""

import re
from dataclasses import dataclass
from pathlib import Path

from app.ordixa.profile import (
    PROFILE_KEYS,
    PROFILE_NAME_PATTERN,
    SCHEMA_VERSION,
    SUPPORTED_FORMATS,
    VERSION_PATTERN,
    AmountRules,
    ProfileError,
    expect_string,
    expect_string_list,
    expect_table,
    parse_amount_rules,
    read_profile_document,
    unknown_keys,
    validate_date_format,
)

WORKFLOW_KINDS = {"clean", "compare"}
# bumped when the meaning of clean/compare outputs changes; recorded in manifests
WORKFLOW_VERSION = 1

# text keeps the trimmed value; identifier keeps exact text with leading zeros;
# decimal is an exact amount; integer is a whole number; date uses the
# declared formats and is written as YYYY-MM-DD
COLUMN_TYPES = {"text", "identifier", "decimal", "integer", "date"}
# integer and decimal keys would merge spellings such as 007 and 7
KEY_TYPES = {"text", "identifier"}
WHITESPACE_RULES = {"trim", "collapse"}

TOP_LEVEL_KEYS = {
    "schema_version",
    "workflow",
    "profile",
    "input",
    "amounts",
    "table",
    "columns",
    "compare",
}
WORKFLOW_KEYS = {"kind"}
INPUT_KEYS = {"formats", "csv_encoding", "sheet"}
TABLE_KEYS = {"key", "blank_values", "date_formats"}
COLUMN_KEYS = {"source", "type", "required", "whitespace"}
COMPARE_KEYS = {"ignore"}

COLUMN_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
MAX_BLANK_TOKEN = 32


@dataclass(frozen=True)
class ColumnSpec:
    """one output column and the source column it is read from"""

    name: str
    source: str
    type: str = "text"
    required: bool = False
    whitespace: str = "trim"


@dataclass(frozen=True)
class ReadSpec:
    """the subset of a dataset specification the file readers need"""

    role: str
    sheet: str | None
    sources: tuple[str, ...]
    optional_columns: frozenset[str]

    def source_columns(self):
        """
        lists the source columns the profile maps
        :returns: ordered tuple of source column names
        """
        return self.sources


@dataclass(frozen=True)
class TableProfile:
    """validated, versioned profile for cleaning or comparing one table"""

    kind: str
    name: str
    version: str
    description: str
    formats: frozenset[str]
    csv_encoding: str
    sheet: str | None
    amounts: AmountRules | None
    key: tuple[str, ...]
    blank_values: frozenset[str]
    date_formats: tuple[str, ...]
    columns: tuple[ColumnSpec, ...]
    ignore: tuple[str, ...]
    source_path: str
    sha256: str

    def column(self, name):
        """
        finds a column specification by output name
        :param name: output column name
        :returns: column specification
        """
        return next(column for column in self.columns if column.name == name)

    def read_spec(self, role):
        """
        builds the specification the CSV/XLSX readers check headers against
        :param role: input role used in messages, such as before or after
        :returns: read specification
        """
        return ReadSpec(
            role=role,
            sheet=self.sheet,
            sources=tuple(column.source for column in self.columns),
            optional_columns=frozenset(
                column.source
                for column in self.columns
                if not column.required and column.name not in self.key
            ),
        )


def parse_column(name, table, problems):
    """
    validates one [columns.<name>] table
    :param name: output column name
    :param table: column table
    :param problems: list collecting validation problems
    :returns: column specification, or none when invalid
    """
    path = f"columns.{name}."
    if not COLUMN_NAME_PATTERN.match(name):
        problems.append(
            f"columns.{name}: output names use lowercase letters, digits, and "
            "underscores, starting with a letter (max 64)"
        )
    if not isinstance(table, dict):
        problems.append(f"columns.{name}: must be a table")
        return None
    unknown_keys(table, COLUMN_KEYS, path, problems)

    source = expect_string(table, "source", path, problems, default="")
    if source and source.strip() != source:
        problems.append(f"{path}source: must not have surrounding spaces")
    column_type = table.get("type", "text")
    if column_type not in COLUMN_TYPES:
        problems.append(f"{path}type: must be one of {sorted(COLUMN_TYPES)}")
        column_type = "text"
    required = table.get("required", False)
    if not isinstance(required, bool):
        problems.append(f"{path}required: must be true or false")
        required = False
    whitespace = table.get("whitespace", "trim")
    if whitespace not in WHITESPACE_RULES:
        problems.append(f"{path}whitespace: must be one of {sorted(WHITESPACE_RULES)}")
        whitespace = "trim"
    elif whitespace != "trim" and column_type != "text":
        problems.append(f"{path}whitespace: only text columns can collapse spaces")

    return ColumnSpec(name, source, column_type, required, whitespace)


def parse_columns(document, problems):
    """
    validates the ordered column mapping
    :param document: parsed TOML document
    :param problems: list collecting validation problems
    :returns: tuple of column specifications in output order
    """
    table = expect_table(document, "columns", "", problems)
    if isinstance(table, dict) and "columns" in document and not table:
        problems.append("columns: map at least one column")

    columns = []
    sources = {}
    for name, column_table in table.items():
        column = parse_column(name, column_table, problems)
        if column is None:
            continue
        if column.source in sources:
            problems.append(
                f"columns.{name}.source: {column.source!r} is already mapped to "
                f"{sources[column.source]!r}"
            )
        sources[column.source] = name
        columns.append(column)
    return tuple(columns)


def parse_table_rules(document, columns, problems):
    """
    validates keys, blank tokens, and date formats
    :param document: parsed TOML document
    :param columns: validated column specifications
    :param problems: list collecting validation problems
    :returns: tuple of key, blank values, and date formats
    """
    table = expect_table(document, "table", "", problems, required=False)
    unknown_keys(table, TABLE_KEYS, "table.", problems)
    by_name = {column.name: column for column in columns}

    key = expect_string_list(table, "key", "table.", problems)
    if len(set(key)) != len(key):
        problems.append("table.key: lists a column more than once")
    for name in key:
        column = by_name.get(name)
        if column is None:
            problems.append(f"table.key: {name!r} is not a mapped column")
        elif column.type not in KEY_TYPES:
            problems.append(
                f"table.key: {name!r} is a {column.type} column; business keys must "
                "be identifier or text columns so spellings are never merged"
            )

    blank_values = expect_string_list(table, "blank_values", "table.", problems)
    for token in blank_values:
        if token.strip() != token or len(token) > MAX_BLANK_TOKEN:
            problems.append(
                f"table.blank_values: {token!r} must have no surrounding spaces and "
                f"at most {MAX_BLANK_TOKEN} characters"
            )

    date_formats = expect_string_list(table, "date_formats", "table.", problems)
    if any(column.type == "date" for column in columns) and not date_formats:
        problems.append(
            "table.date_formats: required because a date column is mapped; dates "
            "are never guessed"
        )
    for date_format in date_formats:
        validate_date_format(date_format, "table.date_formats", problems)

    return tuple(key), frozenset(blank_values), date_formats


def parse_compare_rules(document, kind, columns, key, problems):
    """
    validates the compare-only section
    :param document: parsed TOML document
    :param kind: workflow kind
    :param columns: validated column specifications
    :param key: business key column names
    :param problems: list collecting validation problems
    :returns: tuple of column names left out of the comparison
    """
    if kind != "compare":
        if "compare" in document:
            problems.append("compare: only allowed when workflow.kind is 'compare'")
        return ()

    if not key:
        problems.append(
            "table.key: required for compare; records are matched only by an "
            "explicit business key, never by row position"
        )
    table = expect_table(document, "compare", "", problems, required=False)
    unknown_keys(table, COMPARE_KEYS, "compare.", problems)
    ignore = expect_string_list(table, "ignore", "compare.", problems)
    names = {column.name for column in columns}
    for name in ignore:
        if name not in names:
            problems.append(f"compare.ignore: {name!r} is not a mapped column")
        elif name in key:
            problems.append(f"compare.ignore: {name!r} is a key column")
    return tuple(ignore)


def validate_table_profile(document, source_path="<memory>", sha256=""):
    """
    validates a parsed clean/compare profile document
    :param document: dictionary parsed from TOML
    :param source_path: profile location used in messages
    :param sha256: checksum of the profile file
    :returns: validated table profile
    """
    if "workflow" not in document:
        hint = (
            "; this looks like a reconciliation profile, use python -m app.ordixa run"
            if "datasets" in document
            else ""
        )
        raise ProfileError([f"workflow: required table is missing{hint}"], source_path)

    problems = []
    unknown_keys(document, TOP_LEVEL_KEYS, "", problems)
    schema_version = document.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        problems.append(
            f"schema_version: must be {SCHEMA_VERSION} (found {schema_version!r})"
        )

    workflow = expect_table(document, "workflow", "", problems)
    unknown_keys(workflow, WORKFLOW_KEYS, "workflow.", problems)
    kind = workflow.get("kind")
    if kind not in WORKFLOW_KINDS:
        problems.append(f"workflow.kind: must be one of {sorted(WORKFLOW_KINDS)}")

    meta = expect_table(document, "profile", "", problems)
    unknown_keys(meta, PROFILE_KEYS, "profile.", problems)
    name = expect_string(meta, "name", "profile.", problems, default="")
    version = expect_string(meta, "version", "profile.", problems, default="")
    description = expect_string(
        meta, "description", "profile.", problems, default="", required=False
    )
    if name and not PROFILE_NAME_PATTERN.match(name):
        problems.append(
            "profile.name: use lowercase letters, digits, and hyphens (max 64)"
        )
    if version and not VERSION_PATTERN.match(version):
        problems.append("profile.version: must look like MAJOR.MINOR.PATCH")

    input_table = expect_table(document, "input", "", problems, required=False)
    unknown_keys(input_table, INPUT_KEYS, "input.", problems)
    formats = expect_string_list(
        input_table, "formats", "input.", problems, default=("csv",)
    )
    for input_format in formats:
        if input_format not in SUPPORTED_FORMATS:
            problems.append(
                f"input.formats: {input_format!r} is not supported; "
                f"use {sorted(SUPPORTED_FORMATS)}"
            )
    csv_encoding = expect_string(
        input_table,
        "csv_encoding",
        "input.",
        problems,
        default="utf-8-sig",
        required=False,
    )
    try:
        "".encode(csv_encoding)
    except LookupError:
        problems.append(f"input.csv_encoding: unknown encoding {csv_encoding!r}")
    sheet = expect_string(input_table, "sheet", "input.", problems, required=False)

    columns = parse_columns(document, problems)
    amounts = None
    if any(column.type == "decimal" for column in columns):
        amounts = parse_amount_rules(document, problems)
    elif "amounts" in document:
        problems.append("amounts: only allowed when a decimal column is mapped")

    key, blank_values, date_formats = parse_table_rules(document, columns, problems)
    ignore = parse_compare_rules(document, kind, columns, key, problems)

    if problems:
        raise ProfileError(problems, source_path)

    # key columns are always required, whatever the column table says
    columns = tuple(
        ColumnSpec(c.name, c.source, c.type, True, c.whitespace) if c.name in key else c
        for c in columns
    )
    return TableProfile(
        kind=kind,
        name=name,
        version=version,
        description=description,
        formats=frozenset(formats),
        csv_encoding=csv_encoding,
        sheet=sheet,
        amounts=amounts,
        key=key,
        blank_values=blank_values,
        date_formats=date_formats,
        columns=columns,
        ignore=ignore,
        source_path=str(source_path),
        sha256=sha256,
    )


def is_table_profile_document(document):
    """
    tells clean/compare profiles apart from reconciliation profiles
    :param document: parsed TOML document
    :returns: true when the document declares a workflow
    """
    return "workflow" in document


def load_table_profile(path, kind=None):
    """
    loads and validates a clean/compare profile
    :param path: profile file path
    :param kind: workflow the caller runs, or none to accept either
    :returns: validated table profile
    """
    document, sha256 = read_profile_document(path)
    profile = validate_table_profile(document, source_path=Path(path), sha256=sha256)
    if kind is not None and profile.kind != kind:
        raise ProfileError(
            [
                f"workflow.kind: this profile is for {profile.kind}, not {kind}; "
                f"use python -m app.ordixa {profile.kind}"
            ],
            path,
        )
    return profile
