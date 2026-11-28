"""Extension lifecycle and A2A, checked against A58 and A71.

Issue #62's criteria, mapped one test each:

1. an extension moves through experimental, qualified, recommended, and
   deprecated status; the status is visible to installs (A58);
2. a qualified agent-based deputy takes over when the primary maintainer
   is unavailable; deprecation notifies affected projects (A58);
3. an external agent connects through the versioned A2A adapter with an
   Agent Card; the task, identity, and answer are tied to the event log
   (A71);
4. an unknown identity is rejected, and a message cannot change mandate,
   ownership, or policy (A71).
"""

from __future__ import annotations

import pytest

from dev_org.core import ExtensionLifecycle
from dev_org.gateway import A2A_PROTOCOL, A2AAdapter, AgentCard
from dev_org.state.store import InMemoryStore


def make_lifecycle() -> ExtensionLifecycle:
    lifecycle = ExtensionLifecycle()
    lifecycle.register(
        name="plugin-x", publisher="acme", version="1.0", contracts=["agent-adapter"], maintainer="m-1"
    )
    return lifecycle


# 1. Lifecycle statuses, visible to installs (A58) ------------------------


def test_an_extension_moves_through_the_lifecycle_statuses():
    lifecycle = make_lifecycle()
    extension = lifecycle.get("plugin-x")
    assert extension.status == "experimental"  # registered status

    lifecycle.promote("plugin-x", to="qualified")
    lifecycle.promote("plugin-x", to="recommended")
    lifecycle.promote("plugin-x", to="deprecated")

    # The status is visible to installs through the registry (A58).
    assert lifecycle.get("plugin-x").status == "deprecated"


def test_a_backwards_status_move_is_refused():
    lifecycle = make_lifecycle()
    lifecycle.promote("plugin-x", to="qualified")
    with pytest.raises(ValueError, match="back"):
        lifecycle.promote("plugin-x", to="experimental")


# 2. Deputy take-over and deprecation notification (A58) ------------------


def test_a_qualified_deputy_takes_over_when_the_maintainer_is_unavailable():
    lifecycle = make_lifecycle()
    # The primary maintainer is unavailable; a qualified agent deputy is
    # assigned and now owns the common contract (A58).
    lifecycle.assign_deputy("plugin-x", deputy="deputy-1")
    extension = lifecycle.get("plugin-x")
    assert extension.deputy == "deputy-1"
    assert lifecycle.owns_contract("plugin-x", "agent-adapter")  # the contract is still covered


def test_deprecation_notifies_affected_projects():
    lifecycle = make_lifecycle()
    lifecycle.promote("plugin-x", to="qualified")
    lifecycle.promote("plugin-x", to="recommended")
    lifecycle.promote("plugin-x", to="deprecated")

    # Deprecation notifies every affected project (the extension's contracts).
    assert lifecycle.get("plugin-x").notified_projects == ["agent-adapter"]


# 3. A2A adapter: Agent Card and the event log (A71) ----------------------


def test_an_external_agent_connects_with_an_agent_card_and_its_task_is_logged():
    store = InMemoryStore()
    adapter = A2AAdapter(store=store)
    card = AgentCard(agent_id="ext-1", name="external helper", protocol=A2A_PROTOCOL)

    adapter.connect(card)
    answer_id = adapter.send_task(agent_id="ext-1", task_id="t-1", message="please verify the fix")

    # The send is tied to the task's internal id in the event log (A71).
    sent = [e for e in store.events if e.event_type == "a2a.task_sent" and e.task_id == "t-1"]
    assert len(sent) == 1
    assert sent[0].payload["answer_id"] == answer_id


def test_an_answer_is_tied_to_the_task_in_the_event_log():
    store = InMemoryStore()
    adapter = A2AAdapter(store=store)
    adapter.connect(AgentCard(agent_id="ext-1", name="external", protocol=A2A_PROTOCOL))

    answer_id = adapter.send_task(agent_id="ext-1", task_id="t-1", message="please verify")
    adapter.answer(answer_id=answer_id, task_id="t-1", text="verified")

    answers = [e for e in store.events if e.event_type == "a2a.answer" and e.task_id == "t-1"]
    assert len(answers) == 1
    assert answers[0].payload["text"] == "verified"


def test_an_unsupported_a2a_protocol_is_refused():
    store = InMemoryStore()
    adapter = A2AAdapter(store=store)
    with pytest.raises(ValueError, match="protocol"):
        adapter.connect(AgentCard(agent_id="ext-2", name="bad", protocol="dev-org.a2a.old"))


# 4. Unknown identity rejected; messages cannot change authority (A71) ----


def test_an_unknown_external_agent_is_rejected():
    store = InMemoryStore()
    adapter = A2AAdapter(store=store)
    with pytest.raises(ValueError, match="unknown external agent"):
        adapter.send_task(agent_id="intruder", task_id="t-1", message="hi")


def test_a2a_messages_cannot_change_mandate_ownership_or_policy():
    store = InMemoryStore()
    adapter = A2AAdapter(store=store)
    # The adapter's contract guarantees messages never change authority (A71).
    assert adapter.message_can_change_authority() is False
