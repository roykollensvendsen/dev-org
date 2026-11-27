"""Worker node registration and capability matching, checked against A63/A64.

Issue #49's acceptance criteria, mapped one test each:

1. register a second worker with different capabilities; the scheduler
   only chooses compatible nodes (A63);
2. a node reports heartbeat, program/runner version, engines, and
   CPU/memory/disk; missing measurements are unknown, not zero (A64);
3. combined capacity includes only fresh, qualified nodes; draining,
   offline, revoked, and stale nodes are excluded (A64);
4. worker join registers a node with its actual capacity (section 7.1).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dev_org.agents.protocol import Capabilities
from dev_org.core import NodeRegistry, TaskRequirements

T0 = datetime(2026, 11, 27, 10, 0, tzinfo=UTC)


def node_caps(*, engines: set[str] | None = None, **capabilities: str) -> Capabilities:
    """Capabilities for a node: engine names plus per-capability state."""
    fields: dict[str, str] = dict(capabilities)
    for engine in engines or set():
        fields[f"engine.{engine}"] = "supported"
    return Capabilities(version="1.0", **fields)


# 1. Compatible nodes only (A63) -----------------------------------------


def test_a_second_worker_with_different_capabilities_registers_and_matches():
    registry = NodeRegistry()
    node_a = registry.join(capabilities=node_caps(engines={"opencode"}), cpu=4)
    node_b = registry.join(capabilities=node_caps(engines={"claude-code"}), cpu=2)

    # A task that needs OpenCode can only run on node A.
    requirements = TaskRequirements(
        required_engines=frozenset(), required_capabilities=frozenset({"engine.opencode"})
    )
    qualified = registry.qualified_nodes(requirements, now=T0)
    assert node_a.node_id in [n.node_id for n in qualified]
    assert node_b.node_id not in [n.node_id for n in qualified]


def test_a_node_missing_a_required_capability_is_not_qualified():
    registry = NodeRegistry()
    registry.join(capabilities=node_caps(engines={"opencode"}), cpu=4)

    requirements = TaskRequirements(required_capabilities=frozenset({"usage_measurement"}))
    # The node does not report usage measurement: unavailable, not qualified.
    assert registry.qualified_nodes(requirements, now=T0) == []


def test_an_unreported_capability_is_unknown_not_supported():
    registry = NodeRegistry()
    node = registry.join(capabilities=node_caps(engines={"opencode"}), cpu=4)
    # A capability the node never reports defaults to unavailable (A64).
    assert node.capabilities.something_never_reported == "unavailable"


# 2. Heartbeat, versions, and capacity; unknown is not zero (A64) ---------


def test_a_node_reports_heartbeat_versions_and_capacity():
    registry = NodeRegistry()
    node = registry.join(
        capabilities=node_caps(engines={"opencode"}, usage_measurement="unavailable"), cpu=4, memory_mb=8192
    )
    registry.heartbeat(node.node_id, now=T0)

    assert node.cpu == 4
    assert node.memory_mb == 8192
    assert node.capabilities.version == "1.0"
    assert node.fresh(now=T0) is True


def test_missing_resource_measurement_is_unknown_not_zero():
    registry = NodeRegistry()
    # A node that does not report disk: disk_mb stays None, never 0.
    node = registry.join(capabilities=node_caps(engines={"opencode"}), cpu=4)
    assert node.disk_mb is None


# 3. Combined capacity: only fresh, qualified nodes (A64) -----------------


def test_an_offline_or_revoked_node_is_excluded_from_capacity():
    registry = NodeRegistry()
    active = registry.join(capabilities=node_caps(engines={"opencode"}), cpu=4)
    offline = registry.join(capabilities=node_caps(engines={"opencode"}), cpu=4)
    revoked = registry.join(capabilities=node_caps(engines={"opencode"}), cpu=4)
    registry.set_status(offline.node_id, "offline")
    registry.set_status(revoked.node_id, "revoked")

    requirements = TaskRequirements(required_capabilities=frozenset({"engine.opencode"}))
    qualified = registry.qualified_nodes(requirements, now=T0)
    assert active.node_id in [n.node_id for n in qualified]
    assert offline.node_id not in [n.node_id for n in qualified]
    assert revoked.node_id not in [n.node_id for n in qualified]


def test_a_stale_heartbeat_excludes_a_node():
    registry = NodeRegistry()
    node = registry.join(capabilities=node_caps(engines={"opencode"}), cpu=4)
    registry.heartbeat(node.node_id, now=T0)

    # Two minutes later, the heartbeat is stale (HEARTBEAT_STALE).
    later = T0 + timedelta(minutes=3)
    assert node.fresh(now=later) is False
    requirements = TaskRequirements(required_capabilities=frozenset({"engine.opencode"}))
    assert registry.qualified_nodes(requirements, now=later) == []


def test_draining_stops_new_assignments():
    registry = NodeRegistry()
    node = registry.join(capabilities=node_caps(engines={"opencode"}), cpu=4)
    registry.set_status(node.node_id, "draining")

    requirements = TaskRequirements(required_capabilities=frozenset({"engine.opencode"}))
    assert registry.qualified_nodes(requirements, now=T0) == []


# 4. worker join registers actual capacity (section 7.1) ------------------


def test_join_registers_a_node_with_a_stable_id_and_actual_capacity():
    registry = NodeRegistry()
    node = registry.join(capabilities=node_caps(engines={"codex"}), cpu=8, memory_mb=16384, disk_mb=51200)

    assert node.node_id.startswith("node-")
    assert registry.get(node.node_id) is node
    assert node.cpu == 8
    assert node.memory_mb == 16384
    assert node.disk_mb == 51200
