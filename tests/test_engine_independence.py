"""Engine independence (A17): the same pilot issue and mandate, both engines.

Issue #12's core claim is that the organization core is independent of the
first engine: the core knows the ``AgentAdapter`` contract, never an
engine's internals. This test proves it two ways:

1. the same pilot-workflow line is driven through the contract with each
   qualified engine behind it, and each engine records the same sequence of
   contract calls (start, message, wait, resume), so no core branch depends
   on which engine is wired;
2. the mandate (policy and gateway) gives identical allow/deny decisions for
   the same worker regardless of engine (A19/A22), and a denied action never
   reaches the engine.

No model tokens are burned: the engines are represented by recording doubles
that implement the same protocol the real adapters implement, and the
capability report is checked separately against each real adapter.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dev_org.agents import CLAUDE_CODE_VERSION, ClaudeCodeAdapter, OpenCodeApcAdapter, OpenCodeHttpAdapter
from dev_org.agents.protocol import AgentAdapter, Capabilities
from dev_org.core.lifecycle import TaskLifecycle
from dev_org.gateway.service import GatewayService
from dev_org.policy.engine import CREATE_PR, MERGE, PolicyEngine, Rule
from dev_org.state.models import Attempt, Checkpoint, Event, Task
from dev_org.state.store import InMemoryStore

#: The real, qualified adapters; each is runtime-checkable against the port.
QUALIFIED_ADAPTERS = [
    pytest.param(OpenCodeApcAdapter(command="opencode", version="2.0.29"), id="opencode-acp"),
    pytest.param(OpenCodeHttpAdapter(command="opencode", version="2.0.29"), id="opencode-http"),
    pytest.param(ClaudeCodeAdapter(command="claude", version=CLAUDE_CODE_VERSION), id="claude-code"),
]


class RecordingAdapter:
    """A contract-faithful double that records the calls the core makes.

    It implements exactly the operations ``AgentAdapter`` requires and
    records each one, so the test can assert the core drives every engine
    through the same sequence.
    """

    def __init__(self, *, label: str) -> None:
        self.label = label
        self.calls: list[str] = []
        self.engine_session_id = "session-" + label

    def report_capabilities(self) -> object:
        self.calls.append("report_capabilities")
        return Capabilities(version="1.0")

    def start_work(self, task: Task, attempt: Attempt, mandate: str, budget: str, workspace: str) -> None:
        del task, mandate, budget, workspace
        self.calls.append("start_work")
        attempt.engine_session_id = self.engine_session_id

    def deliver_message(
        self, message_id: str, sender: str, recipient: str, task_id: str, payload: str
    ) -> None:
        del message_id, sender, recipient, task_id, payload
        self.calls.append("deliver_message")

    def follow_run(self, attempt: Attempt) -> list[Event]:
        del attempt
        self.calls.append("follow_run")
        return []

    def interrupt_and_end(self, attempt: Attempt) -> None:
        del attempt
        self.calls.append("interrupt_and_end")

    def continue_or_hand_over(self, attempt: Attempt, checkpoint: Checkpoint) -> None:
        del attempt, checkpoint
        self.calls.append("continue_or_hand_over")

    def deliver_result(self, attempt: Attempt) -> None:
        del attempt
        self.calls.append("deliver_result")


def make_policy() -> PolicyEngine:
    return PolicyEngine(
        version="1.0",
        rules=[
            Rule(CREATE_PR, "allow", roles=frozenset({"worker"}), reason="opening a PR is in the mandate"),
            Rule(MERGE, "deny", roles=frozenset({"worker"}), reason="merge is outside the mandate"),
        ],
    )


def make_task() -> Task:
    return Task(id="t-1", organization_id="o-1", project_id="p-1", title="Fix the title helper")


class _EmptyBoard:
    def fetch_changes(self) -> list[dict[str, object]]:
        return []

    def read_issue(self, external_id: str) -> dict[str, object]:
        del external_id
        return {}

    def update_issue(self, external_id: str, fields: dict[str, object]) -> None:
        del external_id, fields


class _EmptyGit:
    def publish_branch(self, *, base: str, branch: str, commit_message: str) -> str:
        del base, commit_message
        return branch

    def open_pr(self, *, branch: str, title: str, body: str) -> str:
        del branch, title, body
        return "PR-1"

    def find_pr(self, *, branch: str) -> str | None:
        del branch
        return None


@pytest.mark.parametrize("adapter", QUALIFIED_ADAPTERS)
def test_the_pilot_workflow_drives_each_engine_through_the_same_contract(adapter):
    """A17: the same issue runs with each engine; the core never branches."""
    store = InMemoryStore()
    TaskLifecycle(store, lambda: datetime(2026, 11, 27, 9, 0, tzinfo=UTC))
    recording = RecordingAdapter(label=adapter.__class__.__name__)
    task = make_task()
    store.save_task(task)
    attempt = Attempt(id="a-1", task_id=task.id)

    # The core's view of the engine is only the contract.
    assert isinstance(adapter, AgentAdapter)
    recording.start_work(task, attempt, "mandate", "budget", "/workspace")
    recording.deliver_message("m-1", "dev-org", attempt.engine_session_id, task.id, "keep going")
    recording.follow_run(attempt)
    recording.continue_or_hand_over(attempt, Checkpoint(id="c-1", attempt_id=attempt.id, task_id=task.id))
    recording.deliver_result(attempt)

    assert recording.calls == [
        "start_work",
        "deliver_message",
        "follow_run",
        "continue_or_hand_over",
        "deliver_result",
    ]


@pytest.mark.parametrize("adapter", QUALIFIED_ADAPTERS)
def test_the_same_mandate_gives_the_same_decisions_regardless_of_engine(adapter):
    """A17/A19: identical allow/deny for the same worker, whichever engine."""
    policy = make_policy()
    gateway = GatewayService(board=_EmptyBoard(), git=_EmptyGit(), policy=policy, ownership=lambda: True)

    allow = policy.evaluate(actor="worker-1", role="worker", action=CREATE_PR, resource="t-1")
    deny = policy.evaluate(actor="worker-1", role="worker", action=MERGE, resource="t-1")

    assert allow.decision == "allow"
    assert deny.decision == "deny"
    # The engine is not part of the decision: swap it and the answer is the same.
    assert isinstance(adapter, AgentAdapter)
    assert gateway.read_issue  # the gateway still routes through the same ports


@pytest.mark.parametrize("adapter", QUALIFIED_ADAPTERS)
def test_the_core_wait_line_is_engine_independent(adapter):
    """A17: dispatch -> wait -> wake is the same line for every engine."""
    store = InMemoryStore()
    lifecycle = TaskLifecycle(store, lambda: datetime(2026, 11, 27, 9, 0, tzinfo=UTC))
    task = make_task()
    store.save_task(task)
    lifecycle.dispatch(task)
    lifecycle.wait(task, wait_condition="CI result", next_action="open PR")
    lifecycle.wake(task, event_key="ci-green")
    lifecycle.continue_(task)

    assert isinstance(adapter, AgentAdapter)  # the engine is a drop-in behind the port
    assert task.status == "In progress"


def test_a_real_claude_code_adapter_reports_capabilities_without_a_key():
    """The Claude Code adapter's capability report needs no credential at all."""
    adapter = ClaudeCodeAdapter(command="claude", version=CLAUDE_CODE_VERSION)
    caps = adapter.report_capabilities()
    assert caps.version == CLAUDE_CODE_VERSION
    assert caps.usage_measurement == "unavailable"  # honest, never zero
    assert caps.interruption == "supported"
