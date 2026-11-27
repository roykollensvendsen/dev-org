"""The first workflow, end to end: a bug report becomes a verified PR.

Issue #11's pilot demonstrates the complete delivery loop the MVP exists
for, from a bug report on the board to a verified pull request, using the
real components:

- the task lifecycle (issue #5) drives Ready -> In progress -> Waiting ->
  Ready for reprocessing -> Completed;
- the gateway (issue #9) opens the PR once and re-finds it after a restart
  or a lost answer (A01), idempotently (A37/A38);
- CI waiting (issue #10) holds the worker's session while CI runs and wakes
  it once (A02/A11).

Everything runs against the deterministic in-memory store, a simulated
clock, deterministic board/Git/CI doubles, and a simulated worker. This
matches the specification's section 12 method: queue, policy, and the state
machine are tested deterministically with a simulated clock, workers, and
failure injection.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dev_org.core.ci_waiting import CiWaiter
from dev_org.core.lifecycle import COMPLETED, IN_PROGRESS, READY_FOR_REPROCESSING, WAITING, TaskLifecycle
from dev_org.gateway.service import GatewayService
from dev_org.policy.engine import CREATE_PR, PolicyEngine, Rule
from dev_org.state.models import Task
from dev_org.state.store import InMemoryStore

REPO = "roykollensvendsen/dev-org"


class FakeClock:
    """A clock a test can advance without sleeping."""

    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 11, 27, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, minutes: int) -> None:
        self.now += timedelta(minutes=minutes)


class FakeBoard:
    """The board double: the bug report lives here, and the PR link goes back."""

    def __init__(self) -> None:
        self.issues: dict[str, dict[str, object]] = {}
        self.updates: list[tuple[str, dict[str, object]]] = []

    def fetch_changes(self) -> list[dict[str, object]]:
        return [dict(value, external_id=key) for key, value in self.issues.items()]

    def read_issue(self, external_id: str) -> dict[str, object]:
        return dict(self.issues[external_id], external_id=external_id)

    def update_issue(self, external_id: str, fields: dict[str, object]) -> None:
        self.updates.append((external_id, fields))
        self.issues[external_id] = {**self.issues.get(external_id, {}), **fields}


class FakeGit:
    """The Git/PR double: one PR per branch; publishing is idempotent."""

    def __init__(self) -> None:
        self.prs: dict[str, str] = {}
        self.publishes: int = 0

    def publish_branch(self, *, base: str, branch: str, commit_message: str) -> str:
        del base, commit_message
        if branch not in self.prs:
            self.publishes += 1
        return branch

    def open_pr(self, *, branch: str, title: str, body: str) -> str:
        del title, body
        existing = self.find_pr(branch=branch)
        if existing is not None:
            return existing
        number = f"PR-{len(self.prs) + 1}"
        self.prs[branch] = number
        return number

    def find_pr(self, *, branch: str) -> str | None:
        return self.prs.get(branch)


class FakeCi:
    """The CI double: a result per (repo, sha, check)."""

    def __init__(self) -> None:
        self.results: dict[tuple[str, str, str], str] = {}
        self.calls: int = 0

    def check_status(self, *, repo: str, sha: str, check_name: str) -> dict[str, object]:
        self.calls += 1
        return {"state": self.results.get((repo, sha, check_name), "pending")}


def make_policy() -> PolicyEngine:
    return PolicyEngine(
        version="1.0",
        rules=[
            Rule(CREATE_PR, "allow", roles=frozenset({"worker"}), reason="opening a PR is in the mandate")
        ],
    )


def make_gateway(*, board: FakeBoard, git: FakeGit) -> GatewayService:
    return GatewayService(board=board, git=git, policy=make_policy(), ownership=lambda: True)


#: The fixture commit the simulated worker "fixes" on; CI runs against it.
SHA = "abc123"


def branch_for(task: Task) -> str:
    """One branch per delivery, derived from the task's stable ID."""
    return f"devorg-{task.id}-fix-title"


def simulate_worker(
    *,
    lifecycle: TaskLifecycle,
    gateway: GatewayService,
    ci: CiWaiter,
    task: Task,
) -> None:
    """A simulated worker: fix, open the PR, then hold the session on CI.

    The branch and sha are deterministic from the task (one branch per
    delivery, one commit per attempt), so the caller need not repeat them.
    The worker's session ends while CI runs: the duration of CI is not the
    worker's time, so nothing stays up (A11).
    """
    branch = branch_for(task)
    lifecycle.dispatch(task)
    gateway.open_pr(
        actor="worker-1", task_id=task.id, branch=branch, title="Fix the title helper", body="Fixes #1"
    )
    ci.wait_for_ci(task=task, repo=REPO, sha=SHA, check_name="checks", next_action="merge")


def make_rig() -> tuple[InMemoryStore, FakeClock, FakeBoard, FakeGit, FakeCi, Task, str, str]:
    """A full simulated rig and a ready, highest-priority bug-report task."""
    store = InMemoryStore()
    clock = FakeClock()
    board = FakeBoard()
    git = FakeGit()
    ci = FakeCi()
    task = Task(
        id="t-1",
        organization_id="o-1",
        project_id="p-1",
        external_id="GH-1",
        title="Fix the title helper",
        priority="P0",  # type: ignore[arg-type]
    )
    store.save_task(task)
    board.issues["GH-1"] = {"title": task.title, "priority": "P0"}
    return store, clock, board, git, ci, task, branch_for(task), SHA


# The full delivery line ------------------------------------------------


def test_a_bug_report_becomes_a_verified_pr_and_is_delivered_once():
    store, clock, board, git, ci, task, branch, sha = make_rig()

    lifecycle = TaskLifecycle(store, clock)
    gateway = make_gateway(board=board, git=git)
    waiter = CiWaiter(lifecycle=lifecycle, ci=ci, store=store)

    simulate_worker(lifecycle=lifecycle, gateway=gateway, ci=waiter, task=task)

    # The worker's session is ended while CI runs: the task waits (A11).
    assert task.status == WAITING
    recorded = gateway.journal.recorded("open_pr")[-1]
    assert recorded.status == "done"
    assert recorded.external_ref == git.prs[branch]

    # CI comes back green; the wait resolves and one continuation starts.
    clock.advance(minutes=2)
    ci.results[(REPO, sha, "checks")] = "success"
    assert waiter.reconcile(task_id="t-1") == "success"
    assert task.status == READY_FOR_REPROCESSING

    lifecycle.continue_(task)
    assert task.status == IN_PROGRESS
    lifecycle.complete(task)
    assert task.status == COMPLETED

    # Independent check: only one PR exists, and it is linked on the board.
    assert len(git.prs) == 1
    board_after = dict(board.issues).get("t-1") or dict(board.issues).get("GH-1") or {}
    assert board_after["pr_link"] == git.prs[branch]
    assert board_after["status"] != "Ready"


# A01: restart re-finds the same PR and delivers once -------------------


def test_a_restart_re_finds_the_same_pr_and_does_not_open_a_duplicate():
    """A01's interruption point: the PR exists, but registration was lost."""
    store, clock, board, git, ci, task, branch, sha = make_rig()

    lifecycle = TaskLifecycle(store, clock)
    gateway = make_gateway(board=board, git=git)
    waiter = CiWaiter(lifecycle=lifecycle, ci=ci, store=store)

    simulate_worker(lifecycle=lifecycle, gateway=gateway, ci=waiter, task=task)

    # CI has gone green, but the webhook was dropped before the crash; the
    # reconciliation later finds it (A02). A fresh process re-finds the same
    # PR instead of opening a second one (A01), then completes once.
    ci.results[(REPO, sha, "checks")] = "success"
    restarted = make_gateway(board=board, git=git)

    re_found = restarted.open_pr(
        actor="worker-1", task_id="t-1", branch=branch, title="Fix the title helper", body="retry"
    )
    assert re_found == git.prs[branch]
    assert len(git.prs) == 1  # no duplicate even after a restart

    assert waiter.reconcile(task_id="t-1") == "success"
    assert task.status == READY_FOR_REPROCESSING
    lifecycle.continue_(task)
    lifecycle.complete(task)
    assert task.status == COMPLETED
    reprocessing = [e for e in store.events_for_task("t-1") if e.event_type == "task.reprocessing"]
    assert len(reprocessing) == 1  # at most one logical continuation
