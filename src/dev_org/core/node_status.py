"""Node status aggregation and recovery rights.

Implements issue #53 (acceptance tests A24, A64): node status is visible
and correct, and recovery cannot re-introduce revoked rights.

- A64: combined capacity includes only fresh, qualified nodes; draining,
  offline, revoked, old heartbeat, and unknown resources are shown
  correctly and affect available capacity, with drill-down from node to
  task (section 7.1, 8.5).
- A24: restore re-evaluates current mandates; an old image taken before a
  mandate was revoked cannot re-introduce the revoked right, and old test
  evidence does not approve a changed delivery.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from dev_org.core.nodes import HEARTBEAT_STALE

if TYPE_CHECKING:
    from datetime import datetime

    from dev_org.core.nodes import NodeRegistry, TaskRequirements, WorkerNode


@dataclass(frozen=True)
class NodeStatusView:
    """One node's aggregated status for the overview (section 8.5)."""

    node_id: str
    status: str  # active | draining | offline | revoked
    fresh: bool
    heartbeat_stale: bool
    cpu: int | None  # None = unknown, never shown as zero capacity
    memory_mb: int | None
    disk_mb: int | None
    qualified_for_current_work: bool


class NodeStatusService:
    """Aggregate node status and enforce recovery rights."""

    def __init__(self, *, registry: NodeRegistry) -> None:
        """Bind the status service to the node registry."""
        self.registry = registry

    def overview(self, requirements: TaskRequirements, *, now: datetime) -> dict[str, object]:
        """The combined status: qualified capacity and every node's view.

        Aggregated capacity counts only fresh, qualified nodes; draining,
        offline, revoked, stale, and unknown-resource nodes are shown but
        never presented as free capacity (A64, section 8.5).
        """
        qualified = self.registry.qualified_nodes(requirements, now=now)
        views = [self._view(node, requirements=requirements, now=now) for node in self.registry.all_nodes()]
        return {
            "qualified_nodes": len(qualified),
            "registered_nodes": len(self.registry.all_nodes()),
            "nodes": views,
        }

    def drill_down(
        self, node_id: str, requirements: TaskRequirements, *, now: datetime
    ) -> NodeStatusView | None:
        """One node's status, for drill-down from node to task (A64)."""
        node = self.registry.get(node_id)
        if node is None:
            return None
        return self._view(node, requirements=requirements, now=now)

    def _view(self, node: WorkerNode, *, requirements: TaskRequirements, now: datetime) -> NodeStatusView:
        return NodeStatusView(
            node_id=node.node_id,
            status=node.status,
            fresh=node.fresh(now=now),
            heartbeat_stale=node.status == "active" and now - node.last_heartbeat > HEARTBEAT_STALE,
            cpu=node.cpu,
            memory_mb=node.memory_mb,
            disk_mb=node.disk_mb,
            qualified_for_current_work=requirements.satisfied_by(node),
        )

    # -- recovery rights (A24) ------------------------------------------

    def restore_allowed(
        self,
        *,
        image_mandates: frozenset[str],
        current_mandates: frozenset[str],
        test_evidence_version: str,
        code_version: str,
    ) -> bool:
        """Whether a restored image may act under the current mandate.

        A24: the current mandate is checked before action; a mandate the
        image carries that is no longer in the current set was revoked and
        must not be re-introduced, and old test evidence (taken before a
        code change) does not approve the changed delivery.
        """
        revoked = image_mandates - current_mandates
        if revoked:
            return False  # the image would re-introduce revoked rights
        return test_evidence_version == code_version


__all__ = ["NodeStatusService", "NodeStatusView"]
