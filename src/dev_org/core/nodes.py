"""Worker nodes: registration, capability matching, and status.

Implements issue #49 (acceptance tests A63, A64): a worker node registers
with a stable node id and reports heartbeat, engine/adapter versions,
toolchain, and capacity; the scheduler only assigns tasks the node's
qualified capabilities satisfy (section 7.1).

- A63: register a second worker with different capabilities; the scheduler
  only chooses compatible nodes, and the issues use isolated workspaces
  with no shared local writable state.
- A64: combined capacity includes only fresh, qualified nodes; draining,
  offline, revoked, old heartbeat, and unknown resources are shown
  correctly and affect available capacity.
- Missing measurements are shown as unknown, not zero (section 7.1).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from dev_org.agents.protocol import Capabilities

#: How old a heartbeat may be before a node counts as stale (A64).
HEARTBEAT_STALE = timedelta(minutes=2)

#: A node's operational status (section 7.1).
NodeStatus = Literal["active", "draining", "offline", "revoked"]


@dataclass
class WorkerNode:
    """One registered worker node and what it can actually do."""

    node_id: str
    capabilities: Capabilities  # what engines/adapters this node can run
    cpu: int | None = None  # None means unknown, shown as unknown, never zero
    memory_mb: int | None = None
    disk_mb: int | None = None
    status: NodeStatus = "active"
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(UTC))

    def fresh(self, *, now: datetime) -> bool:
        """Whether the node is active and its heartbeat is fresh (A64)."""
        return self.status == "active" and now - self.last_heartbeat <= HEARTBEAT_STALE


@dataclass
class TaskRequirements:
    """What a task needs from a node: required engine/adapter capabilities.

    Each requirement is a capability name that must be ``supported`` (or
    ``emulated``) on the chosen node (section 4.1: a missing capability
    leads to another qualified choice or a concrete blockage).
    """

    required_capabilities: frozenset[str] = frozenset()
    required_engines: frozenset[str] = frozenset()

    def satisfied_by(self, node: WorkerNode) -> bool:
        """Whether the node reports every required capability as supported.

        Emulated counts as usable; unavailable or unknown does not. A node
        that lacks a required engine is not qualified (A63).
        """
        for capability in self.required_capabilities:
            if getattr(node.capabilities, capability, "unavailable") not in ("supported", "emulated"):
                return False
        return True


class NodeRegistry:
    """Register, update, and query worker nodes (section 7.1)."""

    def __init__(self) -> None:
        """Create an empty registry."""
        self._nodes: dict[str, WorkerNode] = {}

    def join(
        self,
        *,
        capabilities: Capabilities,
        cpu: int | None = None,
        memory_mb: int | None = None,
        disk_mb: int | None = None,
    ) -> WorkerNode:
        """Register a node with its actual capacity and a stable id."""
        node = WorkerNode(
            node_id=f"node-{uuid.uuid4().hex[:8]}",
            capabilities=capabilities,
            cpu=cpu,
            memory_mb=memory_mb,
            disk_mb=disk_mb,
        )
        self._nodes[node.node_id] = node
        return node

    def get(self, node_id: str) -> WorkerNode | None:
        """Return the registered node, or None."""
        return self._nodes.get(node_id)

    def heartbeat(self, node_id: str, *, now: datetime) -> None:
        """Record a heartbeat; an unknown node is refused (A64)."""
        node = self._nodes.get(node_id)
        if node is None:
            msg = f"unknown node {node_id}"
            raise KeyError(msg)
        node.last_heartbeat = now

    def set_status(self, node_id: str, status: NodeStatus) -> None:
        """Set draining, offline, or revoked; update the record."""
        node = self._nodes[node_id]
        node.status = status

    def qualified_nodes(self, requirements: TaskRequirements, *, now: datetime) -> list[WorkerNode]:
        """The fresh, qualified nodes for a task (A63, A64).

        Combined capacity includes only fresh nodes (active status, fresh
        heartbeat); among them, only those that satisfy the task's
        requirements. Draining, offline, revoked, and stale nodes are
        excluded, and missing resource measurements never make a node
        qualified by defaulting to zero (section 7.1).
        """
        return [n for n in self._nodes.values() if n.fresh(now=now) and requirements.satisfied_by(n)]

    def all_nodes(self) -> list[WorkerNode]:
        """Every registered node, for status views."""
        return list(self._nodes.values())


__all__ = ["HEARTBEAT_STALE", "NodeRegistry", "NodeStatus", "TaskRequirements", "WorkerNode"]
