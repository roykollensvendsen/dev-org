"""Parallel assignment on isolated nodes, checked against its criteria.

Issue #52's acceptance criteria, mapped one test each, per A04, A26, A63:

1. two issues run on two nodes in isolated workspaces with no shared
   writable state (A63);
2. a shared-contract change identifies affected consumers and gets one
   responsibility point and a transition plan (A26);
3. a third ready issue completes while two are blocked; an answer and a
   freed bench wake only the relevant issue (A04);
4. workspace isolation is structural: two tasks can never be assigned the
   same writable path.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dev_org.agents.protocol import Capabilities
from dev_org.core import (
    NodeLeaseService,
    NodeRegistry,
    ParallelAssignmentService,
    TaskLifecycle,
    Workspace,
    WorkspaceConflictError,
)
from dev_org.state.models import Task
from dev_org.state.store import InMemoryStore

T0 = datetime(2026, 11, 28, 10, 0, tzinfo=UTC)


def make_task(task_id: str) -> Task:
    return Task(id=task_id, organization_id="o-1", project_id="p-1", title=f"Fix {task_id}")


def make_service() -> tuple[ParallelAssignmentService, NodeRegistry]:
    registry = NodeRegistry()
    store = InMemoryStore()
    lifecycle = TaskLifecycle(store, lambda: T0)
    lease = NodeLeaseService(lifecycle=lifecycle, store=store)
    service = ParallelAssignmentService(registry=registry, lease=lease)
    return service, registry


def register_node(registry: NodeRegistry, *, engines: set[str]) -> str:
    caps = Capabilities(version="1.0", **{f"engine.{e}": "supported" for e in engines})
    return registry.join(capabilities=caps).node_id


# 1. Isolated workspaces, no shared writable state (A63) ------------------


def test_two_nodes_run_two_issues_in_isolated_workspaces():
    service, registry = make_service()
    node_a = register_node(registry, engines={"opencode"})
    node_b = register_node(registry, engines={"claude-code"})

    wa = service.assign(task=make_task("t-a"), node_id=node_a, workspace_path="/work/a")
    wb = service.assign(task=make_task("t-b"), node_id=node_b, workspace_path="/work/b")

    assert wa.node_id == node_a
    assert wb.node_id == node_b
    assert not wa.overlaps(wb)  # no shared writable state (A63)
    assert service.workspace_for("t-a") is wa
    assert service.workspace_for("t-b") is wb


def test_two_tasks_cannot_share_a_workspace_path():
    service, registry = make_service()
    node_a = register_node(registry, engines={"opencode"})

    service.assign(task=make_task("t-a"), node_id=node_a, workspace_path="/work/a")
    with pytest.raises(WorkspaceConflictError, match="already in use"):
        service.assign(task=make_task("t-b"), node_id=node_a, workspace_path="/work/a")


# 2. Shared contract: one responsibility point (A26) ---------------------


def test_a_shared_contract_change_has_one_responsibility_point():
    service, _ = make_service()
    change = service.register_contract_change(
        contract="agent-adapter",
        responsible_worker="worker-1",
        affected_consumers=["worker-2", "worker-3"],
        transition_plan="land v2, then migrate consumers one at a time",
    )

    assert change.responsible_worker == "worker-1"
    assert change.affected_consumers == ["worker-2", "worker-3"]
    assert change.transition_plan
    # The owner covers it; another worker is a consumer, not the owner.
    assert change.covers("worker-1") is True
    assert change.covers("worker-2") is False


def test_a_contract_owner_is_queryable_for_planning():
    service, _ = make_service()
    service.register_contract_change(
        contract="queue", responsible_worker="w-1", affected_consumers=["w-2"], transition_plan="migrate"
    )
    owner = service.contract_owner("queue")
    assert owner is not None
    assert owner.responsible_worker == "w-1"
    assert service.contract_owner("unknown-contract") is None


# 3. A third issue completes while two are blocked (A04) ------------------


def test_an_answer_wakes_only_the_issue_it_belongs_to():
    store = InMemoryStore()
    lifecycle = TaskLifecycle(store, lambda: T0)

    # Two issues are blocked: one on a domain choice, one on a bench.
    domain = make_task("t-domain")
    bench = make_task("t-bench")
    third = make_task("t-third")
    for task in (domain, bench, third):
        store.save_task(task)
    lifecycle.dispatch(domain)
    lifecycle.dispatch(bench)
    lifecycle.wait(domain, wait_condition="user answer", next_action="apply the fix")
    lifecycle.wait(bench, wait_condition="bench free", next_action="run the test")

    # The third ready issue completes while the other two are blocked (A04).
    lifecycle.dispatch(third)
    lifecycle.complete(third)
    assert third.status == "Completed"

    # A user answer wakes only the domain issue, not the bench one.
    lifecycle.wake(domain, event_key="user-answer-1")
    assert domain.status == "Ready for reprocessing"
    assert bench.status == "Waiting"  # the bench issue is untouched


def test_a_freed_bench_wakes_only_the_bench_issue():
    store = InMemoryStore()
    lifecycle = TaskLifecycle(store, lambda: T0)

    domain = make_task("t-domain")
    bench = make_task("t-bench")
    for task in (domain, bench):
        store.save_task(task)
    lifecycle.dispatch(domain)
    lifecycle.dispatch(bench)
    lifecycle.wait(domain, wait_condition="user answer", next_action="apply")
    lifecycle.wait(bench, wait_condition="bench free", next_action="run")

    lifecycle.wake(bench, event_key="bench-free-1")
    assert bench.status == "Ready for reprocessing"
    assert domain.status == "Waiting"  # the domain issue stays blocked


# 4. Structural isolation (A63) ------------------------------------------


def test_workspace_overlap_is_structural():
    # Two workspaces with the same path overlap; different paths do not.
    a = Workspace(node_id="node-1", path="/work/shared")
    b = Workspace(node_id="node-2", path="/work/shared")
    c = Workspace(node_id="node-3", path="/work/other")
    assert a.overlaps(b) is True
    assert a.overlaps(c) is False
