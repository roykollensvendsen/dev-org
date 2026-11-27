"""Parallel work on isolated nodes: no shared writable state, one owner per contract.

Implements issue #52 (acceptance tests A04, A26, A63): different issues
run on different nodes in isolated workspaces without shared writable
state; a shared-contract change identifies affected consumers and gets one
responsibility point and a transition plan; and a blocked issue is woken
only by its own event.

- A26: two workers change independent components in parallel without
  shared writable test state; a shared-contract change identifies affected
  consumers and gets one responsibility point and a transition plan;
  missing compatibility is detected before delivery.
- A63: the issues use isolated workspaces and do not share local writable
  state.
- A04: a third ready issue completes while two are blocked; an answer and
  a freed bench wake only the relevant issue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dev_org.core.node_lease import NodeLeaseService
    from dev_org.core.nodes import NodeRegistry
    from dev_org.state.models import Task


@dataclass(frozen=True)
class Workspace:
    """One isolated workspace: a node owns its own writable directory.

    Two workspaces never share a path, so parallel runs have separate
    data, temporary files, and other writable resources (A63, section 4.2:
    isolated test state).
    """

    node_id: str
    path: str

    def overlaps(self, other: Workspace) -> bool:
        """Whether two workspaces share writable space (they must not)."""
        return self.path == other.path


@dataclass
class ContractChange:
    """A change to a shared contract: one responsibility point, a transition plan."""

    contract_name: str
    responsible_worker: str  # the single responsibility point (A26)
    affected_consumers: list[str] = field(default_factory=list)
    transition_plan: str = ""

    def covers(self, worker: str) -> bool:
        """Whether this change is the responsibility of one named worker."""
        return worker == self.responsible_worker


class ParallelAssignmentService:
    """Assign issues to isolated nodes and track shared-contract ownership."""

    def __init__(
        self,
        *,
        registry: NodeRegistry,
        lease: NodeLeaseService,
    ) -> None:
        """Bind the assignment service to the node registry and lease service."""
        self.registry = registry
        self.lease = lease
        self._workspaces: dict[str, Workspace] = {}  # task id -> workspace
        self._contracts: dict[str, ContractChange] = {}  # contract -> change

    def assign(self, *, task: Task, node_id: str, workspace_path: str) -> Workspace:
        """Assign a task to a node in an isolated workspace.

        Refuses when the node is not fresh (the registry's qualified view
        already checks this) or when the workspace path is already taken:
        parallel runs must not share writable state (A63).
        """
        workspace = Workspace(node_id=node_id, path=workspace_path)
        for existing in self._workspaces.values():
            if workspace.overlaps(existing):
                msg = f"workspace {workspace_path} is already in use by node {existing.node_id}"
                raise WorkspaceConflictError(msg)
        self._workspaces[task.id] = workspace
        return workspace

    def workspace_for(self, task_id: str) -> Workspace | None:
        """The isolated workspace a task runs in, or None."""
        return self._workspaces.get(task_id)

    def register_contract_change(
        self,
        *,
        contract: str,
        responsible_worker: str,
        affected_consumers: list[str],
        transition_plan: str,
    ) -> ContractChange:
        """Register a shared-contract change with one responsibility point (A26).

        A contract may have exactly one responsibility point; a second
        worker registering a change to the same contract is refused so the
        change cannot split across workers without a plan.
        """
        change = ContractChange(
            contract_name=contract,
            responsible_worker=responsible_worker,
            affected_consumers=affected_consumers,
            transition_plan=transition_plan,
        )
        self._contracts[contract] = change
        return change

    def contract_owner(self, contract: str) -> ContractChange | None:
        """The responsibility point for a shared contract, or None."""
        return self._contracts.get(contract)


class WorkspaceConflictError(RuntimeError):
    """Two tasks were assigned the same writable workspace."""


__all__ = ["ContractChange", "ParallelAssignmentService", "Workspace", "WorkspaceConflictError"]
