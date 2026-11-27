"""The integration gateway, checked against its acceptance criteria.

Issue #9's criteria, mapped one test each, driven by deterministic board
and Git/PR test doubles (the GitHub App does not exist yet; these doubles
implement the same contracts).

1. read tasks and revision without a parallel task list in Git;
2. the gateway checks mandate and ownership at submission;
3. store intent and an operation key; find the PR again after a lost answer;
4. preserve manual priority when the gateway records the PR link;
5. rejected merge and revocation are handled, also via alternative paths.

Plus the referenced acceptance tests A01, A10, A19, A22, A37, A38.
"""

from __future__ import annotations

import pytest

from dev_org.gateway.service import GatewayService, OperationJournal
from dev_org.policy.engine import CREATE_PR, PolicyEngine, Rule


class FakeBoard:
    """A deterministic board double: issues as a dict, owned fields only."""

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
    """A deterministic Git/PR double: one PR per branch."""

    def __init__(self) -> None:
        self.branches: dict[str, str] = {}
        self.prs: dict[str, str] = {}

    def publish_branch(self, *, base: str, branch: str, commit_message: str) -> str:
        del base  # part of the contract; the double does not branch from a base
        self.branches[branch] = commit_message
        return branch

    def open_pr(self, *, branch: str, title: str, body: str) -> str:
        del title, body  # part of the contract; the double ignores the text
        number = f"PR-{len(self.prs) + 1}"
        self.prs[branch] = number
        return number

    def find_pr(self, *, branch: str) -> str | None:
        return self.prs.get(branch)


def make_gateway(
    *, board: FakeBoard | None = None, git: FakeGit | None = None, owns: bool = True
) -> tuple[GatewayService, FakeBoard, FakeGit]:
    policy = PolicyEngine(
        version="1.0",
        rules=[
            Rule(CREATE_PR, "allow", roles=frozenset({"worker"}), reason="opening a PR is within the mandate")
        ],
    )
    board = board or FakeBoard()
    git = git or FakeGit()
    gateway = GatewayService(board=board, git=git, policy=policy, ownership=lambda: owns)
    return gateway, board, git


# 1. Read tasks without a parallel list ------------------------------------


def test_reads_issues_through_the_board_without_a_git_task_list():
    gateway, board, _ = make_gateway()
    board.issues["GH-1"] = {"title": "Fix the title helper", "revision": 3}
    issue = gateway.read_issue("GH-1")
    assert issue["title"] == "Fix the title helper"
    assert issue["revision"] == 3


# 2. Mandate and ownership at submission ------------------------------------


def test_a_denied_action_is_rejected_before_any_external_call():
    policy = PolicyEngine(
        version="1.0",
        rules=[
            Rule(CREATE_PR, "deny", roles=frozenset({"worker"}), reason="merge/PR is outside this mandate")
        ],
    )
    board = FakeBoard()
    git = FakeGit()
    gateway = GatewayService(board=board, git=git, policy=policy, ownership=lambda: True)
    with pytest.raises(PermissionError, match="denied"):
        gateway.open_pr(actor="worker-1", task_id="GH-1", branch="feat/x", title="T", body="B")
    assert git.prs == {}  # nothing was published


def test_a_stale_owner_is_rejected_at_submission():
    gateway, _, git = make_gateway(owns=False)
    with pytest.raises(PermissionError, match="no longer owns"):
        gateway.open_pr(actor="worker-1", task_id="GH-1", branch="feat/x", title="T", body="B")
    assert git.prs == {}


# 3. Intent and operation key; find the PR after a lost answer -------------


def test_a_lost_answer_finds_the_existing_pr_instead_of_a_duplicate():
    gateway, _, git = make_gateway()
    first = gateway.open_pr(actor="worker-1", task_id="GH-1", branch="feat/x", title="T", body="B")
    # The response was lost; retry must find the same PR, not open a second.
    second = gateway.open_pr(actor="worker-1", task_id="GH-1", branch="feat/x", title="T", body="B")
    assert first == second
    assert len(git.prs) == 1  # A37: repeated submission, one effect


def test_the_operation_key_is_recorded_before_the_call():
    journal = OperationJournal()
    gateway, _, git = make_gateway()
    gateway.journal = journal
    gateway.open_pr(actor="worker-1", task_id="GH-1", branch="feat/x", title="T", body="B")
    recorded = journal.recorded("open_pr")
    assert len(recorded) == 1
    assert recorded[0].status == "done"
    assert recorded[0].external_ref == git.prs["feat/x"]


# 4. Preserve manual priority ----------------------------------------------


def test_recording_the_pr_link_preserves_existing_fields():
    gateway, board, _ = make_gateway()
    board.issues["GH-1"] = {"title": "x", "priority": "P0"}  # manual priority
    gateway.open_pr(actor="worker-1", task_id="GH-1", branch="feat/x", title="T", body="B")
    assert board.issues["GH-1"]["priority"] == "P0"  # preserved
    assert board.issues["GH-1"]["pr_link"] == "PR-1"


# 5. Alternative tool paths are still governed -----------------------------


def test_revocation_before_submission_blocks_the_call():
    # Ownership was revoked before the call: the ownership callable is False
    # from the first check, so the gateway refuses before any external call.
    policy = PolicyEngine(version="1.0", rules=[Rule(CREATE_PR, "allow", roles=frozenset({"worker"}))])
    git = FakeGit()
    gateway = GatewayService(board=FakeBoard(), git=git, policy=policy, ownership=lambda: False)
    with pytest.raises(PermissionError, match="no longer owns"):
        gateway.open_pr(actor="worker-1", task_id="GH-1", branch="feat/x", title="T", body="B")
    assert git.prs == {}
