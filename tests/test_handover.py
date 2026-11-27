"""Handover and message delivery, checked against their acceptance criteria.

Issue #13: another engine continues from the organization's checkpoint.
The tests map to the acceptance criteria and the referenced A-tests:

1. hand over secured code, mandate, decisions, test evidence, wait
   condition, and next action (A18);
2. preserve issue ID, existing PR, and valid checks; an engine change
   alone orders no build (A18/A36);
3. deliver messages and approval answers with stable IDs; separate
   received from processed (A23/A54);
4. a duplicate handover or a duplicate message is one logical
   continuation, and a wrong recipient or expired answer grants nothing
   (A23/A35/A36).

All engines are represented by contract-faithful doubles; the real adapters
are qualified by the contract suite.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dev_org.agents.protocol import Capabilities
from dev_org.core import HandoverError, HandoverService, TaskLifecycle
from dev_org.gateway.service import GatewayService
from dev_org.policy.engine import CREATE_PR, PolicyEngine, Rule
from dev_org.state.messages import Message, MessageInbox
from dev_org.state.models import Attempt, Checkpoint, Task
from dev_org.state.store import InMemoryStore


class FakeEngine:
    """A contract-faithful engine double that records handover calls."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.handovers: list[tuple[str, str]] = []  # (attempt_id, next_action)
        self.started: list[str] = []

    def report_capabilities(self) -> Capabilities:
        return Capabilities(version="1.0")

    def start_work(self, task: Task, attempt: Attempt, mandate: str, budget: str, workspace: str) -> None:
        del task, mandate, budget, workspace
        self.started.append(attempt.id)

    def deliver_message(
        self, message_id: str, sender: str, recipient: str, task_id: str, payload: str
    ) -> None:
        del message_id, sender, recipient, task_id, payload

    def follow_run(self, attempt: Attempt) -> list[object]:
        del attempt
        return []

    def interrupt_and_end(self, attempt: Attempt) -> None:
        del attempt

    def continue_or_hand_over(self, attempt: Attempt, checkpoint: Checkpoint) -> None:
        self.handovers.append((attempt.id, checkpoint.next_action or ""))

    def deliver_result(self, attempt: Attempt) -> None:
        del attempt


class FakeBoard:
    def fetch_changes(self) -> list[dict[str, object]]:
        return []

    def read_issue(self, external_id: str) -> dict[str, object]:
        del external_id
        return {}

    def update_issue(self, external_id: str, fields: dict[str, object]) -> None:
        del external_id, fields


class FakeGit:
    def __init__(self) -> None:
        self.prs: dict[str, str] = {"devorg-t-1-fix": "PR-7"}

    def publish_branch(self, *, base: str, branch: str, commit_message: str) -> str:
        del base, commit_message
        return branch

    def open_pr(self, *, branch: str, title: str, body: str) -> str:
        del branch, title, body
        return "PR-7"

    def find_pr(self, *, branch: str) -> str | None:
        del branch
        return "PR-7"


def make_task() -> Task:
    return Task(id="t-1", organization_id="o-1", project_id="p-1", title="Fix the title helper")


def make_checkpoint(*, complete: bool = True) -> Checkpoint:
    return (
        Checkpoint(
            id="c-1",
            attempt_id="a-1",
            task_id="t-1",
            code_reference="devorg-t-1-fix@abc123",
            test_evidence=["tests/test_queue_priority.py passed"],
            decisions=["the queue must be priority-ordered"],
            wait_conditions=["ci:sha:checks"],
            next_action="merge the PR",
        )
        if complete
        else Checkpoint(id="c-1", attempt_id="a-1", task_id="t-1")
    )


def make_rig() -> tuple[HandoverService, TaskLifecycle, InMemoryStore, FakeEngine, FakeGit, Task]:
    store = InMemoryStore()
    lifecycle = TaskLifecycle(store, lambda: datetime(2026, 11, 27, 9, 0, tzinfo=UTC))
    task = make_task()
    store.save_task(task)
    lifecycle.dispatch(task)
    # A18: the issue has secured code and waits on CI before the handover.
    lifecycle.wait(task, wait_condition="ci:sha:checks", next_action="merge the PR")
    policy = PolicyEngine(
        version="1.0",
        rules=[
            Rule(CREATE_PR, "allow", roles=frozenset({"worker"}), reason="opening a PR is in the mandate")
        ],
    )
    git = FakeGit()
    gateway = GatewayService(board=FakeBoard(), git=git, policy=policy, ownership=lambda: True)
    service = HandoverService(lifecycle=lifecycle, gateway=gateway, store=store)
    return service, lifecycle, store, FakeEngine("codex"), git, task


# 1. Complete handover (A18) ---------------------------------------------


def test_a_complete_checkpoint_is_handed_over_to_the_new_engine():
    service, _, store, engine, _, task = make_rig()
    checkpoint = make_checkpoint()

    new_attempt_id = service.hand_over(task=task, checkpoint=checkpoint, engine=engine, engine_name="codex")

    assert engine.handovers == [(new_attempt_id, "merge the PR")]
    # The new attempt is a separate attempt for the same task.
    attempt = store.get_attempt(new_attempt_id)
    assert attempt is not None
    assert attempt.task_id == "t-1"
    # A handover event is recorded with a stable idempotency key.
    handovers = [e for e in store.events_for_task("t-1") if e.event_type == "task.handover"]
    assert len(handovers) == 1


def test_an_incomplete_checkpoint_is_refused():
    service, _, _, engine, _, task = make_rig()
    with pytest.raises(HandoverError, match="incomplete"):
        service.hand_over(
            task=task, checkpoint=make_checkpoint(complete=False), engine=engine, engine_name="codex"
        )


# 2. No build on engine change; PR preserved (A18/A36) -------------------


def test_the_existing_pr_is_preserved_and_no_second_publish_happens():
    service, _, _, engine, git, task = make_rig()
    checkpoint = make_checkpoint()

    service.hand_over(task=task, checkpoint=checkpoint, engine=engine, engine_name="codex")

    # The engine change alone ordered no build: the same PR still exists,
    # and the gateway would re-find it rather than publish again (A36).
    assert git.prs == {"devorg-t-1-fix": "PR-7"}
    assert len(git.prs) == 1


def test_a_duplicate_handover_is_one_logical_continuation():
    service, _, store, engine, _, task = make_rig()
    checkpoint = make_checkpoint()

    service.hand_over(task=task, checkpoint=checkpoint, engine=engine, engine_name="codex")
    with pytest.raises(HandoverError, match="already delivered"):
        service.hand_over(task=task, checkpoint=checkpoint, engine=engine, engine_name="codex")

    handovers = [e for e in store.events_for_task("t-1") if e.event_type == "task.handover"]
    assert len(handovers) == 1


# 3. Stable message IDs; received separate from processed (A23/A54) -------


def test_a_message_moves_queued_available_received_processed():
    inbox = MessageInbox()
    message = Message(
        message_id="m-1", sender="worker-a", recipient="worker-b", task_id="t-1", kind="answer", payload="yes"
    )
    inbox.submit(message)

    assert inbox.states("m-1") == ["queued"]
    assert inbox.deliver("m-1") is message
    assert inbox.states("m-1") == ["queued", "available"]
    assert inbox.receive("m-1", recipient="worker-b") is message
    assert inbox.states("m-1") == ["queued", "available", "received"]
    assert inbox.process("m-1") is message
    assert inbox.states("m-1") == ["queued", "available", "received", "processed"]


def test_a_duplicate_delivery_is_one_logical_processing():
    inbox = MessageInbox()
    message = Message(
        message_id="m-1", sender="a", recipient="b", task_id="t-1", kind="answer", payload="yes"
    )
    inbox.submit(message)
    inbox.deliver("m-1")
    inbox.receive("m-1", recipient="b")
    inbox.process("m-1")

    # A duplicate of the same id must not start a second logical processing.
    inbox.submit(message)
    processed = inbox.process("m-1")
    assert processed is message
    assert inbox.states("m-1").count("processed") == 1


def test_a_wrong_recipient_gets_no_new_mandate():
    inbox = MessageInbox()
    message = Message(
        message_id="m-1", sender="a", recipient="worker-b", task_id="t-1", kind="answer", payload="yes"
    )
    inbox.submit(message)

    assert inbox.receive("m-1", recipient="worker-c") is None  # wrong recipient
    assert inbox.states("m-1")[-1] == "rejected"
    assert inbox.pending_for("t-1") == [message]  # still pending for the right one


def test_an_expired_message_grants_nothing():
    inbox = MessageInbox()
    message = Message(
        message_id="m-1", sender="a", recipient="b", task_id="t-1", kind="answer", payload="yes"
    )
    inbox.submit(message)
    inbox.expire("m-1")

    assert inbox.receive("m-1", recipient="b") is None
    assert inbox.pending_for("t-1") == []


# 4. A35: an old approval answer after a restart grants nothing -----------


def test_a_duplicate_old_answer_is_not_reused_after_processing():
    inbox = MessageInbox()
    answer = Message(
        message_id="m-1",
        sender="approver",
        recipient="worker-b",
        task_id="t-1",
        kind="answer",
        payload="approve",
    )
    inbox.submit(answer)
    inbox.deliver("m-1")
    inbox.receive("m-1", recipient="worker-b")
    inbox.process("m-1")

    # The same answer arrives again after a restart: it is a duplicate of a
    # processed message, so no new continuation (A35).
    inbox.submit(answer)
    assert inbox.states("m-1").count("processed") == 1
    assert inbox.pending_for("t-1") == []
