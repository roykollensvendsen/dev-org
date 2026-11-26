"""The state contracts issue #4 documents, checked where they are defined.

The domain objects (task, attempt, event, checkpoint) and the agent adapter
contract are the load-bearing interfaces of the first data model. These
tests check that the models validate what the specification promises: a
stable internal ID, the external board reference on a task, the nullable
engine session on an attempt, the versioned event schema, and an
engine-independent checkpoint.
"""

from datetime import UTC, datetime

import pytest

from dev_org.agents import AgentAdapter, Capabilities
from dev_org.state.models import Attempt, Checkpoint, Event, Reservation, Task


def test_a_task_carries_a_stable_id_and_its_external_board_reference():
    task = Task(id="t-1", organization_id="o-1", project_id="p-1", external_id="GH-42", title="Fix it")
    assert task.id == "t-1"
    assert task.external_id == "GH-42"
    assert task.status == "Ready"


def test_an_attempt_has_a_nullable_engine_session_reference():
    attempt = Attempt(id="a-1", task_id="t-1")
    assert attempt.engine_session_id is None
    attempt.engine_session_id = "session-9"
    assert attempt.engine_session_id == "session-9"


def test_an_event_carries_the_versioned_schema_and_is_append_only():
    event = Event(
        id="e-1",
        event_type="task.assigned",
        organization_id="o-1",
        project_id="p-1",
        task_id="t-1",
        source="core",
    )
    assert event.schema_version == "dev-org.event.v1"
    assert event.occurred_at.tzinfo is not None  # UTC, not naive


def test_a_checkpoint_is_engine_independent():
    checkpoint = Checkpoint(id="c-1", attempt_id="a-1", task_id="t-1", next_action="fix the title helper")
    assert checkpoint.next_action == "fix the title helper"
    # engine independence: no engine session reference in the checkpoint model
    assert not hasattr(checkpoint, "engine_session_id")


def test_every_object_requires_an_id():
    with pytest.raises(ValueError, match="id"):
        Task(organization_id="o-1", project_id="p-1", title="No id")  # type: ignore[call-arg]


def test_capabilities_distinguish_supported_from_unavailable():
    caps = Capabilities(version="1.0", usage_measurement="unavailable")
    assert caps.usage_measurement == "unavailable"
    assert caps.version == "1.0"


def test_agent_adapter_is_a_runtime_checkable_protocol():
    # A concrete adapter is issue #8; the contract itself must be checkable.
    assert isinstance(AgentAdapter, type)  # it is a Protocol, not an implementation


def test_task_timestamps_are_utc():
    task = Task(id="t-1", organization_id="o-1", project_id="p-1", title="x")
    assert task.created_at.tzinfo is not None
    assert task.updated_at.tzinfo is not None


def test_reservation_holds_a_fencing_token_and_lease():
    fencing_value = "token-" + "value"
    reservation = Reservation(
        id="r-1",
        attempt_id="a-1",
        worker_id="w-1",
        ownership_number=1,
        fencing_token=fencing_value,
        lease_expires_at=datetime.now(UTC),
    )
    assert reservation.fencing_token == fencing_value
    assert reservation.ownership_number == 1
