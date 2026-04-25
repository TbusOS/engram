"""Types shared by all doctor check modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class CheckIssue:
    """A single doctor finding.

    ``code`` is a stable identifier (``DOC-LAYOUT-001`` style) third-party
    tools can grep for. ``fix_command`` is a runnable shell command — the
    contract is that running it should make this issue go away (or get
    significantly closer to gone).
    """

    code: str
    severity: Severity
    message: str
    fix_command: str
    file: str | None = None


@dataclass
class DoctorReport:
    issues: list[CheckIssue] = field(default_factory=list)

    def is_healthy(self) -> bool:
        """No errors AND no warnings → healthy. INFO does not block."""
        return all(i.severity is Severity.INFO for i in self.issues)

    def has_errors(self) -> bool:
        return any(i.severity is Severity.ERROR for i in self.issues)
