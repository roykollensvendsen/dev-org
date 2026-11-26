"""Agent adapter module: the engine-independent contract for an agent engine.

The contract is fixed by the specification (section 4.1): a real engine is
reached through an adapter that implements these operations. This module
defines the contract only; the OpenCode adapter that implements it is issue
#8. The core knows this contract and not the engine's internal protocol.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dev_org.state.models import Attempt, Checkpoint, Event, Task


class Capabilities:
    """What an engine supports, per section 4.1.

    Each capability is one of ``supported``, ``emulated``, or
    ``unavailable``. A missing capability must lead to another qualified
    choice or a concrete blockage; it must not be assumed or hidden.
    """

    def __init__(self, *, version: str, **capabilities: str) -> None:
        """Record the engine version and its per-capability state."""
        self.version = version
        self.capabilities = capabilities

    def __getattr__(self, name: str) -> str:
        """Read a capability by its name, defaulting to unavailable."""
        return self.capabilities.get(name, "unavailable")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        """A short, stable representation for logs."""
        return f"Capabilities(version={self.version})"


@runtime_checkable
class AgentAdapter(Protocol):
    """The common agent adapter contract (section 4.1)."""

    def report_capabilities(self) -> Capabilities:
        """Report what the engine supports, emulates, or lacks."""
        ...

    def start_work(self, task: Task, attempt: Attempt, mandate: str, budget: str, workspace: str) -> None:
        """Start one attempt; a repeated start must not create a second owner."""
        ...

    def deliver_message(
        self, message_id: str, sender: str, recipient: str, task_id: str, payload: str
    ) -> None:
        """Deliver a message tied to the task, distinct from a result."""
        ...

    def follow_run(self, attempt: Attempt) -> list[Event]:
        """Yield normalized events for status, progress, and blockage."""
        ...

    def interrupt_and_end(self, attempt: Attempt) -> None:
        """Confirm actual stop, what is secured, and what still runs."""
        ...

    def continue_or_hand_over(self, attempt: Attempt, checkpoint: Checkpoint) -> None:
        """Resume the session, or continue from the organization's checkpoint."""
        ...

    def deliver_result(self, attempt: Attempt) -> None:
        """Return artifacts, evidence, unresolved items, and next action."""
        ...


__all__ = ["AgentAdapter", "Capabilities"]
