"""Node status and recovery rights, checked against A24 and A64.

Issue #53's criteria, mapped one test each:

1. combined capacity includes only fresh, qualified nodes; draining,
   offline, revoked, stale heartbeat, and unknown resources are shown
   correctly (A64, section 8.5);
2. drill-down from node to task preserves the status (A64);
3. an old image taken before a mandate was revoked cannot re-introduce
   the revoked right (A24);
4. old test evidence does not approve a changed delivery (A24).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dev_org.agents.protocol import Capabilities
from dev_org.core import NodeRegistry, NodeStatusService, TaskRequirements

T0 = datetime(2026, 11, 28, 10, 0, tzinfo=UTC)


def node_caps(engines: set[str]) -> Capabilities:
    return Capabilities(version="1.0", **{f"engine.{e}": "supported" for e in engines})


def make_service() -> tuple[NodeStatusService, NodeRegistry]:
    registry = NodeRegistry()
    return NodeStatusService(registry=registry), registry


def requirements() -> TaskRequirements:
    return TaskRequirements(required_capabilities=frozenset({"engine.opencode"}))


# 1. Combined capacity: fresh, qualified nodes only (A64) -----------------


def test_combined_capacity_includes_only_fresh_qualified_nodes():
    service, registry = make_service()
    active = registry.join(capabilities=node_caps({"opencode"}), cpu=4)
    draining = registry.join(capabilities=node_caps({"opencode"}), cpu=4)
    offline = registry.join(capabilities=node_caps({"opencode"}), cpu=4)
    revoked = registry.join(capabilities=node_caps({"opencode"}), cpu=4)
    stale = registry.join(capabilities=node_caps({"opencode"}), cpu=4)
    for node in (active, draining, offline, revoked, stale):
        registry.heartbeat(node.node_id, now=T0)
    registry.set_status(draining.node_id, "draining")
    registry.set_status(offline.node_id, "offline")
    registry.set_status(revoked.node_id, "revoked")
    registry.heartbeat(stale.node_id, now=T0 - timedelta(minutes=5))  # stale

    overview = service.overview(requirements(), now=T0)
    # Only the active, fresh node counts as qualified capacity (A64).
    assert overview["qualified_nodes"] == 1
    assert overview["registered_nodes"] == 5


def test_each_node_status_is_shown_correctly_not_hidden():
    service, registry = make_service()
    draining = registry.join(capabilities=node_caps({"opencode"}), cpu=4)
    registry.set_status(draining.node_id, "draining")

    overview = service.overview(requirements(), now=T0)
    draining_view = next(v for v in overview["nodes"] if v.node_id == draining.node_id)
    assert draining_view.status == "draining"
    assert draining_view.fresh is False  # not counted as capacity


def test_missing_resource_measurement_is_unknown_not_free_capacity():
    service, registry = make_service()
    # A node with no disk report: disk_mb is None, never shown as 0.
    node = registry.join(capabilities=node_caps({"opencode"}), cpu=4)
    view = service.drill_down(node.node_id, requirements(), now=T0)
    assert view is not None
    assert view.disk_mb is None
    assert view.cpu == 4


# 2. Drill-down preserves the link (A64) ---------------------------------


def test_drill_down_returns_the_node_status_for_an_operator():
    service, registry = make_service()
    node = registry.join(capabilities=node_caps({"opencode"}), cpu=8)

    view = service.drill_down(node.node_id, requirements(), now=T0)
    assert view is not None
    assert view.node_id == node.node_id
    assert view.status == "active"
    assert view.qualified_for_current_work is True


def test_drill_down_for_an_unknown_node_returns_none():
    service, _ = make_service()
    assert service.drill_down("node-nope", requirements(), now=T0) is None


# 3. Recovery cannot re-introduce revoked rights (A24) -------------------


def test_an_old_image_cannot_re_introduce_a_revoked_mandate():
    service, _ = make_service()
    # The image carries "merge"; the current mandate set dropped it.
    assert (
        service.restore_allowed(
            image_mandates=frozenset({"publish_branch", "create_pr", "merge"}),
            current_mandates=frozenset({"publish_branch", "create_pr"}),  # merge revoked
            test_evidence_version="v1",
            code_version="v1",
        )
        is False
    )


def test_a_mandate_revoked_after_the_image_cannot_be_re_introduced():
    service, _ = make_service()
    # The image was taken when "merge" was allowed; it was revoked before
    # restore, so restoring the image would re-introduce the revoked right.
    assert (
        service.restore_allowed(
            image_mandates=frozenset({"publish_branch", "merge"}),
            current_mandates=frozenset({"publish_branch"}),  # merge dropped
            test_evidence_version="v1",
            code_version="v1",
        )
        is False
    )


# 4. Old test evidence does not approve a changed delivery (A24) ---------


def test_old_test_evidence_does_not_approve_a_changed_delivery():
    service, _ = make_service()
    # The image's mandates match the current set, but CI went green on old
    # evidence while the code changed: not approved (A24).
    assert (
        service.restore_allowed(
            image_mandates=frozenset({"publish_branch"}),
            current_mandates=frozenset({"publish_branch"}),
            test_evidence_version="v1",
            code_version="v2",  # code changed after the evidence
        )
        is False
    )


def test_matching_mandate_and_evidence_allow_the_restore():
    service, _ = make_service()
    # Current mandate is unchanged and evidence matches the code.
    assert (
        service.restore_allowed(
            image_mandates=frozenset({"publish_branch"}),
            current_mandates=frozenset({"publish_branch"}),
            test_evidence_version="v2",
            code_version="v2",
        )
        is True
    )
