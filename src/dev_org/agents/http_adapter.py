"""OpenCode adapter over its HTTP API.

The fallback adapter for issue #8, per ADR-DEV-005: it implements the same
``AgentAdapter`` protocol (section 4.1) but reaches OpenCode through its
own HTTP API (`session.create`, `session.prompt`) instead of ACP. This is
the escape hatch if the ACP adapter hits a gap; the core cannot tell the
two apart.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

from dev_org.agents.protocol import Capabilities

if TYPE_CHECKING:
    from dev_org.state.models import Attempt, Checkpoint, Event, Task


class OpenCodeHttpAdapter:
    """Talk to a running OpenCode background service over its HTTP API."""

    def __init__(self, *, command: str = "opencode", version: str = "0.0.0") -> None:
        """Bind the adapter to the engine command and a pinned version."""
        self.command = command
        self.version = version

    def _api(
        self, operation: str, payload: dict[str, object] | None = None, params: dict[str, str] | None = None
    ) -> dict[str, object]:
        """Call one OpenCode API operation via the `opencode api` CLI."""
        args = [self.command, "api", operation]
        for key, value in (params or {}).items():
            args += ["--param", f"{key}={value}"]
        if payload is not None:
            args += ["--data", json.dumps(payload)]
        result = subprocess.run(args, capture_output=True, text=True, check=True)  # noqa: S603
        parsed: object = json.loads(result.stdout)
        if not isinstance(parsed, dict):
            msg = f"expected a JSON object from {operation}, got {type(parsed).__name__}"
            raise TypeError(msg)
        return parsed

    def report_capabilities(self) -> Capabilities:
        """OpenCode supports the full worker contract; the version is pinned."""
        return Capabilities(version=self.version)

    # -- AgentAdapter contract -------------------------------------------

    def start_work(self, task: Task, attempt: Attempt, mandate: str, budget: str, workspace: str) -> None:
        """Start one attempt; a repeated start must not create a second owner."""
        created = self._api("session.create", {"directory": workspace})
        data = created["data"]
        if not isinstance(data, dict):
            msg = "session.create returned no session data"
            raise TypeError(msg)
        session_id = data.get("id")
        if not isinstance(session_id, str):
            msg = "session.create returned no session id"
            raise TypeError(msg)
        attempt.engine_session_id = session_id
        message = f"Start task {task.id}: {task.title}\nMandate: {mandate}\nBudget: {budget}"
        self.deliver_message(f"start-{task.id}", "dev-org", session_id, task.id, message)

    def deliver_message(
        self, message_id: str, sender: str, recipient: str, task_id: str, payload: str
    ) -> None:
        """Deliver a message tied to the task, distinct from a result.

        OpenCode's HTTP API exposes this as `session.prompt` with a `text`
        payload (verified against the live server); the operation is
        `POST /api/session/{sessionID}/prompt`.
        """
        del message_id, sender, task_id  # the prompt carries the content; IDs are logged by the core
        self._api(
            "session.prompt",
            {"text": payload},
            params={"sessionID": recipient},
        )

    def follow_run(self, attempt: Attempt) -> list[Event]:
        """Yield normalized events for status, progress, and blockage."""
        msg = "session/list status arrives with issue #10"
        raise NotImplementedError(msg)

    def interrupt_and_end(self, attempt: Attempt) -> None:
        """Confirm actual stop, what is secured, and what still runs."""
        msg = "interrupt lands with the interrupt test in #10"
        raise NotImplementedError(msg)

    def continue_or_hand_over(self, attempt: Attempt, checkpoint: Checkpoint) -> None:
        """Resume the session, or continue from the organization's checkpoint."""
        msg = "session.export/import lands with the handover test in #10"
        raise NotImplementedError(msg)

    def deliver_result(self, attempt: Attempt) -> None:
        """Return artifacts, evidence, unresolved items, and next action."""
        msg = "result delivery lands with the pilot in #11"
        raise NotImplementedError(msg)
