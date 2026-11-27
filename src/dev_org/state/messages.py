"""Message channel: stable message IDs, received separated from processed.

Implements issue #13's message part (acceptance tests A23, A54): each
message has a stable ``message_id``, recipients handle duplicates
idempotently, and the service records separately that a message is queued,
available, received, processed, rejected, or expired (section 8.3). A
duplicate delivery of the same message_id is one logical processing; a
message for the wrong recipient or an expired approval grants no new
mandate (A23).

A message does not change task ownership, reservation, mandate, or
authority (section 8.3): it is data for the recipient, never an action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Message:
    """One durable message, with delivery state tracked separately."""

    message_id: str
    sender: str
    recipient: str
    task_id: str
    kind: str  # question | answer | status | handover | result
    payload: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    #: Delivery state: queued -> available -> received -> processed, or
    #: rejected/expired. Received and processed are recorded separately.
    state: str = "queued"
    thread_id: str | None = None
    reply_to: str | None = None


class MessageInbox:
    """Record message delivery state, idempotently, per message id."""

    def __init__(self) -> None:
        """Create an empty inbox."""
        self._by_id: dict[str, Message] = {}
        self._states: list[tuple[str, str, datetime]] = []

    def submit(self, message: Message) -> None:
        """Queue a message; a duplicate of the same id is a no-op."""
        if message.message_id in self._by_id:
            return  # idempotent: the first submission is the one logical message
        self._by_id[message.message_id] = message
        self._record(message.message_id, "queued")

    def deliver(self, message_id: str) -> Message | None:
        """Mark a queued message available (received by the channel), once."""
        message = self._by_id.get(message_id)
        if message is None or message.state in ("processed", "expired", "rejected"):
            return None
        if message.state in ("available", "received"):
            return message  # duplicate delivery: one logical message
        message.state = "available"
        self._record(message_id, "available")
        return message

    def receive(self, message_id: str, *, recipient: str) -> Message | None:
        """The recipient marks a message received; wrong recipient gets nothing."""
        message = self._by_id.get(message_id)
        if message is None:
            return None
        if message.recipient != recipient:
            self._record(message_id, "rejected")
            return None  # wrong recipient: no new mandate (A23)
        if message.state == "processed":
            return message  # already handled: the answer is not reused
        if message.state == "expired":
            return None
        message.state = "received"
        self._record(message_id, "received")
        return message

    def process(self, message_id: str) -> Message | None:
        """Mark an available/received message processed, once."""
        message = self._by_id.get(message_id)
        if message is None or message.state == "processed":
            return message
        if message.state not in ("available", "received"):
            return None
        message.state = "processed"
        self._record(message_id, "processed")
        return message

    def expire(self, message_id: str) -> None:
        """Expire a message (e.g. an approval answer past its validity)."""
        message = self._by_id.get(message_id)
        if message is None:
            return
        message.state = "expired"
        self._record(message_id, "expired")

    def states(self, message_id: str) -> list[str]:
        """Every recorded delivery state for a message, in order."""
        return [kind for mid, kind, _ in self._states if mid == message_id]

    def pending_for(self, task_id: str) -> list[Message]:
        """Messages for a task that are not yet processed, in submission order."""
        return [
            m
            for m in self._by_id.values()
            if m.task_id == task_id and m.state not in ("processed", "expired")
        ]

    def _record(self, message_id: str, kind: str) -> None:
        """Append one delivery-state record."""
        self._states.append((message_id, kind, datetime.now(UTC)))


__all__ = ["Message", "MessageInbox"]
