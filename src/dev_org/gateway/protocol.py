"""Gateway module: the only path for external side effects.

The integration gateway (section 3.1) enforces mandates and active
ownership for external actions, and is the only control-plane service that
calls the adapters' mutating operations. No core, worker, API, or MCP code
writes directly to the board, Git, CI, or other external targets.

The contracts live here so the gateway service and the adapters can import
them without a circular import.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Gateway(Protocol):
    """Perform one external action under the current mandate."""

    def submit(self, *, actor: str, operation: str, payload: dict[str, object]) -> str:
        """Submit one external call and return its stable operation key."""
        ...


@runtime_checkable
class BoardAdapter(Protocol):
    """A board's read/write contract (section 4)."""

    def fetch_changes(self) -> list[dict[str, object]]:
        """Return external ID, revision, and changed fields since last fetch."""
        ...

    def read_issue(self, external_id: str) -> dict[str, object]:
        """Return one issue with its dependencies in the common work model."""
        ...

    def update_issue(self, external_id: str, fields: dict[str, object]) -> None:
        """Update only the owned fields of an issue."""
        ...


@runtime_checkable
class GitPrAdapter(Protocol):
    """The Git/PR contract (section 4): publish a branch and one PR."""

    def publish_branch(self, *, base: str, branch: str, commit_message: str) -> str:
        """Publish a branch and return its reference/revision."""
        ...

    def open_pr(self, *, branch: str, title: str, body: str) -> str:
        """Open one PR for a branch and return its PR number."""
        ...

    def find_pr(self, *, branch: str) -> str | None:
        """Find the existing PR for a branch, or None (idempotent retry)."""
        ...
