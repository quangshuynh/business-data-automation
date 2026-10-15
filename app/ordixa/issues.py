from dataclasses import dataclass

ERROR = "error"
WARNING = "warning"
EXCLUDED = "excluded"

# row outcomes shown to reviewers
OUTCOME_LABELS = {
    ERROR: "Rejected",
    WARNING: "Kept with warning",
    EXCLUDED: "Excluded by profile",
}


@dataclass(frozen=True)
class Issue:
    """
    a data-quality finding for one source row

    errors reject the row, warnings keep it, and excluded rows are omitted from
    totals on purpose because the profile says they moved no money
    """

    dataset: str
    file: str
    row: int
    severity: str
    code: str
    message: str
    record_id: str = ""
    field: str = ""
    value: str = ""
    original_values: str = ""

    @property
    def blocking(self):
        """
        reports whether the issue prevented the row from being processed
        :returns: true for errors
        """
        return self.severity == ERROR

    def sort_key(self):
        """
        provides a deterministic ordering for reports
        :returns: tuple used for sorting
        """
        order = {"customers": 0, "orders": 1, "payments": 2}
        return (order.get(self.dataset, 9), self.file, self.row, self.code)


class InputError(ValueError):
    """error raised when input files cannot be discovered or interpreted"""
