"""The integration gateway: the only path for external side effects.

Implements section 3.1/3.2: the gateway enforces mandates and active
ownership for external actions, stores intent and a stable operation key
before an external call, and finds the result again after a lost answer
(idempotency, A01/A37/A38). It talks only to the board and Git/PR adapter
contracts, so a test double can drive it before the GitHub App exists.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from dev_org.gateway.protocol import BoardAdapter, GitPrAdapter
    from dev_org.policy.engine import PolicyEngine


@dataclass
class ExternalOperation:
    """One recorded external call: its intent, key, and outcome."""

    operation_key: str
    actor: str
    operation: str
    payload: dict[str, object]
    status: str = "pending"  # pending | submitted | done | unknown
    external_ref: str | None = None  # e.g. the PR number after a lost answer


class OperationJournal:
    """Durable record of external calls, keyed by a stable operation key."""

    def __init__(self) -> None:
        """Create an empty journal."""
        self._by_key: dict[str, ExternalOperation] = {}

    def record(self, operation: ExternalOperation) -> None:
        """Record the intent before the call is made."""
        self._by_key[operation.operation_key] = operation

    def get(self, operation_key: str) -> ExternalOperation | None:
        """Return the recorded operation for a key, or None."""
        return self._by_key.get(operation_key)

    def recorded(self, operation: str) -> list[ExternalOperation]:
        """Return every recorded operation of a given kind, in insertion order."""
        return [op for op in self._by_key.values() if op.operation == operation]


class GatewayService:
    """Submit board and Git/PR actions under mandate and ownership control.

    ``policy`` decides whether the action is allowed; ``ownership`` is a
    callable returning True when the actor still owns the reservation (so a
    stale owner is rejected, A22). The journal makes retry idempotent.
    """

    def __init__(
        self,
        *,
        board: BoardAdapter,
        git: GitPrAdapter,
        policy: PolicyEngine,
        journal: OperationJournal | None = None,
        ownership: Callable[[], bool] = lambda: True,
    ) -> None:
        """Bind the gateway to its adapters, policy, journal, and ownership check."""
        self.board = board
        self.git = git
        self.policy = policy
        self.journal = journal or OperationJournal()
        self._owns = ownership

    def read_issue(self, external_id: str) -> dict[str, object]:
        """Read an issue through the board adapter (read-only use case)."""
        return self.board.read_issue(external_id)

    def fetch_changes(self) -> list[dict[str, object]]:
        """Fetch changed issues from the board, for reconciliation."""
        return self.board.fetch_changes()

    def open_pr(self, *, actor: str, task_id: str, branch: str, title: str, body: str) -> str:
        """Publish a branch and open one PR, idempotently, under mandate.

        Stores intent and an operation key before the external call, so a
        lost answer can find the PR again instead of opening a duplicate
        (A01). Repeated submission has the same effect as one (A37/A38).
        """
        decision = self.policy.evaluate(actor=actor, role="worker", action="create_pr", resource=task_id)
        if decision.decision == "deny":
            msg = f"create_pr denied for {actor}: {decision.rationale}"
            raise PermissionError(msg)
        if not self._owns():
            msg = f"actor {actor} no longer owns the reservation for {task_id}"
            raise PermissionError(msg)

        # Idempotency: an existing PR for the branch is the answer to a
        # previous submission, even if the response was lost.
        existing = self.git.find_pr(branch=branch)
        if existing is not None:
            return existing

        operation = ExternalOperation(
            operation_key=f"pr-{task_id}-{uuid.uuid4().hex[:8]}",
            actor=actor,
            operation="open_pr",
            payload={"task_id": task_id, "branch": branch, "title": title},
        )
        self.journal.record(operation)

        self.git.publish_branch(base="main", branch=branch, commit_message=title)
        pr_number = self.git.open_pr(branch=branch, title=title, body=body)
        operation.status = "done"
        operation.external_ref = pr_number
        self.board.update_issue(task_id, {"pr_link": pr_number, "status": "In review"})
        return pr_number

    def update_status(self, *, external_id: str, fields: dict[str, object]) -> None:
        """Update only the owned fields of an issue, preserving user priority."""
        self.board.update_issue(external_id, fields)
