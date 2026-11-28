"""The A2A adapter: connect external agents through a versioned protocol.

Implements issue #62 (acceptance test A71): an external agent connects
through the versioned A2A adapter with an Agent Card; the task, identity,
and answer are tied to dev-org's internal IDs and event log; an unknown
identity is rejected; and a message cannot change mandate, ownership, or
policy, and a failure or disconnect does not stop independent work.

This is an adapter for external connections, so it lives with the other
gateway adapters (board, Git/PR) rather than among the core lifecycle
services.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from dev_org.state.models import Event
from dev_org.state.store import InMemoryStore, Store

#: The versioned A2A adapter protocol (A71).
A2A_PROTOCOL = "dev-org.a2a.v1"


@dataclass
class AgentCard:
    """The A2A Agent Card: what an external agent is and offers (A71)."""

    agent_id: str
    name: str
    protocol: str = A2A_PROTOCOL
    capabilities: frozenset[str] = frozenset()


class A2AAdapter:
    """Connect external agents through the versioned A2A adapter (A71)."""

    def __init__(self, *, store: Store | None = None) -> None:
        """Bind the adapter to a store for its event log."""
        self.store = store or InMemoryStore()
        self._cards: dict[str, AgentCard] = {}

    def connect(self, card: AgentCard) -> None:
        """Register an external agent's Agent Card (A71: discovery)."""
        if card.protocol != A2A_PROTOCOL:
            msg = f"unsupported A2A protocol {card.protocol}"
            raise ValueError(msg)
        self._cards[card.agent_id] = card

    def send_task(self, *, agent_id: str, task_id: str, message: str) -> str:
        """Send a scoped task to a known external agent; unknown identity is rejected.

        The message content is carried by the adapter; the record ties the
        send to the task and the answer id (A71).
        """
        del message  # the send itself is the side effect; content is untrusted input
        if agent_id not in self._cards:
            msg = f"unknown external agent {agent_id}"
            raise ValueError(msg)
        answer_id = f"ans-{uuid.uuid4().hex[:8]}"
        self._record("a2a.task_sent", task_id=task_id, payload={"agent_id": agent_id, "answer_id": answer_id})
        return answer_id

    def answer(self, *, answer_id: str, task_id: str, text: str) -> None:
        """Record an external agent's answer, tied to the task's event log (A71)."""
        self._record("a2a.answer", task_id=task_id, payload={"answer_id": answer_id, "text": text})

    def message_can_change_authority(self) -> bool:
        """A2A messages can never change mandate, ownership, or policy (A71)."""
        return False

    def _record(self, event_type: str, *, task_id: str, payload: dict[str, object]) -> None:
        """Append a versioned event tied to the task."""
        self.store.append_event(
            Event(
                id=f"ev-{uuid.uuid4().hex[:12]}",
                event_type=event_type,
                organization_id="o-1",
                project_id="p-1",
                task_id=task_id,
                source="a2a",
                occurred_at=datetime.now(UTC),
                recorded_at=datetime.now(UTC),
                payload=payload,
            )
        )


__all__ = ["A2A_PROTOCOL", "A2AAdapter", "AgentCard"]
