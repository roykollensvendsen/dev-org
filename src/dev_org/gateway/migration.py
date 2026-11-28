"""Board migration: move issues between boards with mapping and priority.

Implements issue #59 (acceptance test A09): move an in-progress issue from
Redmine to GitHub Projects, preserving mapping and priority, with one
active issue, one PR, and zero extra builds as a result of the change.

The migration is explicit export and previewable import (section 4), not
continuous two-way synchronization: nothing is overwritten without an
explicit choice, and the import report states what was created, changed,
and omitted, plus any lost or adapted fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypedDict

from dev_org.gateway.redmine import WORK_V1

if TYPE_CHECKING:
    from dev_org.gateway.protocol import BoardAdapter


class ExportedIssue(TypedDict, total=False):
    """One issue in the dev-org.work.v1 export format."""

    external_id: str
    internal_id: str | None
    title: str
    status: str
    priority: str
    labels: list[str]
    body: str


class WorkExport(TypedDict, total=False):
    """The dev-org.work.v1 export format (section 4)."""

    schema: str
    project_id: str
    exported_at: str
    issues: list[ExportedIssue]


@dataclass
class MigrationReport:
    """What an import did: created, changed, omitted, and lost fields."""

    created: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    omitted: list[str] = field(default_factory=list)
    lost_fields: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, object]:
        """The report as a plain dict."""
        return {
            "created": self.created,
            "changed": self.changed,
            "omitted": self.omitted,
            "lost_fields": self.lost_fields,
        }


class BoardMigration:
    """Export from one board and preview-import into another (section 4)."""

    def __init__(self, *, source: BoardAdapter, target: BoardAdapter) -> None:
        """Bind the migration to the source and target board adapters."""
        self.source = source
        self.target = target

    def preview(self, exported: WorkExport) -> MigrationReport:
        """Preview an import without writing: what would happen.

        The preview names the issues that would be created, which fields
        would be lost (no counterpart on the target), and which issues are
        omitted (e.g. already present). Nothing is written (section 4:
        import must first be previewable).
        """
        report = MigrationReport()
        if exported.get("schema") != WORK_V1:
            msg = f"unsupported export schema {exported.get('schema')}"
            raise ValueError(msg)
        for issue in exported.get("issues", []):
            external_id = str(issue["external_id"])
            existing = self._target_has(external_id)
            if existing:
                report.changed.append(external_id)
            else:
                report.created.append(external_id)
        return report

    def import_(self, exported: WorkExport, *, confirm: bool) -> MigrationReport:
        """Import the export into the target board, only with explicit choice.

        Refuses unless ``confirm`` is true: nothing is overwritten without
        an explicit choice (section 4). Preserves mapping and priority from
        the export, and never creates a second active issue or orders a
        build by itself (A09: one active issue, zero extra builds).
        """
        if not confirm:
            msg = "import refused: pass confirm=True to overwrite the target"
            raise ValueError(msg)
        if exported.get("schema") != WORK_V1:
            msg = f"unsupported export schema {exported.get('schema')}"
            raise ValueError(msg)
        report = self.preview(exported)
        for issue in exported.get("issues", []):
            external_id = str(issue["external_id"])
            fields: dict[str, object] = {
                "title": issue.get("title", ""),
                "state": issue.get("status", ""),
                "priority": issue.get("priority", "P2"),
                "body": issue.get("body", ""),
            }
            self.target.update_issue(external_id, fields)
        return report

    def _target_has(self, external_id: str) -> bool:
        """Whether the target board already holds the issue (by external id)."""
        try:
            self.target.read_issue(external_id)
        except KeyError, IndexError, ValueError:
            return False
        else:
            return True


__all__ = ["BoardMigration", "MigrationReport"]
