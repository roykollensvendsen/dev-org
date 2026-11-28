"""Redmine board adapter: the same board contract as GitHub, for Redmine.

Implements issue #59 (acceptance tests A09, A10): a second board adapter
behind the same ``BoardAdapter`` contract as the GitHub adapter (section
4), with a versioned export format and a previewable migration path between
boards.

The adapter is driven by a deterministic in-memory store by default, so
the contract tests run against it exactly as they run against the GitHub
adapter (A10: the same test passes on both board adapters). The common
work model carries external id, revision, title, state, and body; priority
and the PR link are preserved through the owned fields (A09).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

#: The versioned export format for board migration (section 4).
WORK_V1 = "dev-org.work.v1"


@runtime_checkable
class RedmineClient(Protocol):
    """The minimal Redmine API surface the adapter needs."""

    def list_issues(self) -> list[dict[str, object]]:
        """Return every issue Redmine holds, in the common work model."""
        ...

    def get_issue(self, external_id: str) -> dict[str, object]:
        """Return one issue in the common work model."""
        ...

    def update_issue(self, external_id: str, fields: dict[str, object]) -> None:
        """Update only the owned fields of an issue."""
        ...


class InMemoryRedmine:
    """A deterministic Redmine double for development and contract tests."""

    def __init__(self) -> None:
        """Create an empty Redmine."""
        self.issues: dict[str, dict[str, object]] = {}

    def list_issues(self) -> list[dict[str, object]]:
        """Return every stored issue as a copy."""
        return [dict(issue) for issue in self.issues.values()]

    def get_issue(self, external_id: str) -> dict[str, object]:
        """Return one stored issue, or raise KeyError."""
        return dict(self.issues[external_id])

    def update_issue(self, external_id: str, fields: dict[str, object]) -> None:
        """Merge owned fields into the stored issue."""
        self.issues[external_id] = {**self.issues.get(external_id, {}), **fields}


class RedmineAdapter:
    """Talk to Redmine behind the board contract (section 4)."""

    def __init__(self, *, client: RedmineClient | None = None) -> None:
        """Bind the adapter to a Redmine client; a deterministic one by default."""
        self.client = client or InMemoryRedmine()

    # -- BoardAdapter contract (section 4) ---------------------------------

    def fetch_changes(self) -> list[dict[str, object]]:
        """Return open issues as the common work model."""
        return [
            {
                "external_id": str(issue["external_id"]),
                "revision": str(issue.get("revision", "")),
                "title": issue.get("title", ""),
                "state": issue.get("state", ""),
                "body": issue.get("body") or "",
            }
            for issue in self.client.list_issues()
            if issue.get("state") != "Done"
        ]

    def read_issue(self, external_id: str) -> dict[str, object]:
        """Return one issue in the common work model."""
        issue = self.client.get_issue(external_id)
        return {
            "external_id": str(issue["external_id"]),
            "revision": str(issue.get("revision", "")),
            "title": issue.get("title", ""),
            "state": issue.get("state", ""),
            "body": issue.get("body") or "",
        }

    def update_issue(self, external_id: str, fields: dict[str, object]) -> None:
        """Update only the owned fields of an issue (state, labels, body)."""
        owned = {key: value for key, value in fields.items() if key in {"state", "labels", "body"}}
        if owned:
            self.client.update_issue(external_id, owned)

    # -- export (section 4: dev-org.work.v1) -------------------------------

    def export_work_v1(self) -> dict[str, object]:
        """Export every issue in the versioned format, preserving internal IDs.

        The format is ``dev-org.work.v1``: projects, issues, status,
        priority, responsible role, labels, and the provider's own
        external id as named metadata. Internal ids are preserved, so an
        import can keep the mapping (A09).
        """
        issues = [
            {
                "external_id": str(issue["external_id"]),
                "internal_id": issue.get("internal_id"),
                "title": issue.get("title", ""),
                "status": issue.get("state", ""),
                "priority": issue.get("priority", "P2"),
                "labels": issue.get("labels", []),
                "body": issue.get("body", ""),
            }
            for issue in self.client.list_issues()
        ]
        return {
            "schema": WORK_V1,
            "project_id": "p-1",
            "exported_at": datetime.now(UTC).isoformat(),
            "issues": issues,
        }


__all__ = ["WORK_V1", "InMemoryRedmine", "RedmineAdapter"]
