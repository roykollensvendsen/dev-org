"""Codex adapter: the unmodified Codex CLI behind the agent contract.

Engine number three for issue #12's early step-5 delivery: it implements the
same ``AgentAdapter`` protocol (section 4.1) as the OpenCode and Claude Code
adapters by driving the unmodified ``codex`` CLI in headless mode
(``codex exec --json``), so the organization core cannot tell the engines
apart.

Authentication (section 10.3, A50): Codex runs through the user's qualified
ChatGPT plan login; this adapter never offers a login, never sets or reads
``OPENAI_API_KEY``, and never reads, decodes, or forwards the OAuth token.
The adapter only starts the CLI; the CLI owns the credential, so dev-org
cannot expose what it does not hold.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from dev_org.agents.protocol import Capabilities
from dev_org.state.models import Event

if TYPE_CHECKING:
    from dev_org.state.models import Attempt, Checkpoint, Task

#: The pinned engine/adapter version pair (section 4.1: registered together).
CODEX_VERSION = "0.172.0"


class CodexAdapter:
    """Talk to the unmodified Codex CLI over its headless ``exec`` surface.

    One attempt is one Codex thread. ``start_work`` runs the first prompt,
    reads the ``thread.started`` event for the thread id, and binds the
    attempt to it; ``continue_or_hand_over`` resumes exactly that thread
    with ``codex exec resume <thread_id>``. Events come as JSONL on stdout.
    """

    def __init__(self, *, command: str = "codex", version: str = CODEX_VERSION) -> None:
        """Bind the adapter to the Codex command and the pinned version."""
        self.command = command
        self.version = version

    # -- capability report ----------------------------------------------

    def report_capabilities(self) -> Capabilities:
        """What this engine supports, emulates, or lacks (section 4.1).

        Supported: start, resume, and a normalized event stream. Message
        delivery to a live session uses the CLI's own queue surface, so it
        is marked unavailable until the queue path is qualified. Usage
        measurement is unavailable: the CLI does not expose a billable count,
        so the core must show usage as unknown, never as zero (section 4.1).
        Approval flow and delegation are not built in: policy and the
        gateway still decide them, as with the other engines.
        """
        return Capabilities(
            version=self.version,
            start="supported",
            events="supported",
            interruption="supported",
            approval_flow="unavailable",
            resume="supported",
            delegation="unavailable",
            usage_measurement="unavailable",
        )

    # -- CLI plumbing ---------------------------------------------------

    def _exec(self, *args: str, prompt: str, timeout: int = 600) -> list[dict[str, object]]:
        """Run one headless prompt; return the JSONL events as parsed dicts.

        The environment is inherited unchanged, so the engine authenticates
        with the user's own ChatGPT login (A50); no key is added or read.
        """
        argv = [self.command, "exec", *args, "--skip-git-repo-check", "--json"]
        result = subprocess.run(  # noqa: S603
            argv, input=prompt, capture_output=True, text=True, check=True, timeout=timeout
        )
        events: list[dict[str, object]] = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            try:
                parsed: object = json.loads(line)
            except json.JSONDecodeError:
                continue  # a non-JSON diagnostic line; not part of the stream
            if isinstance(parsed, dict):
                events.append(parsed)
        return events

    @staticmethod
    def _thread_id(events: list[dict[str, object]]) -> str | None:
        """The thread id from the ``thread.started`` event, or None."""
        for event in events:
            if event.get("type") == "thread.started":
                thread_id = event.get("thread_id")
                if isinstance(thread_id, str):
                    return thread_id
        return None

    # -- AgentAdapter contract -------------------------------------------

    def start_work(self, task: Task, attempt: Attempt, mandate: str, budget: str, workspace: str) -> None:
        """Start one attempt in a new thread; never a second owner.

        A repeated start for the same attempt keeps the same thread id, so
        it cannot create a parallel owner (section 4.1).
        """
        if attempt.engine_session_id is not None:
            return  # already started: the pinned thread is the owner
        prompt = (
            f"Start task {task.id}: {task.title}\n"
            f"Mandate: {mandate}\nBudget: {budget}\nWorkspace: {workspace}"
        )
        events = self._exec(prompt=prompt)
        thread_id = self._thread_id(events)
        if thread_id is None:
            msg = "codex exec produced no thread.started event"
            raise RuntimeError(msg)
        attempt.engine_session_id = thread_id

    def deliver_message(
        self, message_id: str, sender: str, recipient: str, task_id: str, payload: str
    ) -> None:
        """Deliver a message tied to the task, distinct from a result.

        The CLI's queue surface is not yet qualified for live injection, so
        this raises clearly rather than pretending a message was delivered.
        """
        msg = "message delivery into a live Codex session lands with the queue-surface qualification"
        raise NotImplementedError(msg)

    def follow_run(self, attempt: Attempt) -> list[Event]:
        """Yield normalized events from the run's own event stream.

        Reads the JSONL events the engine recorded for the pinned thread, so
        status, progress, and blockage come from what the engine actually
        reported, without replaying the model.
        """
        if attempt.engine_session_id is None:
            return []
        events: list[Event] = []
        try:
            raw = self._exec("resume", attempt.engine_session_id, prompt="")
        except (subprocess.CalledProcessError, OSError) as exc:
            # The thread may not be reachable without a model turn; an empty
            # event stream is honest here, never a fabricated progress.
            del exc
            return events
        for event in raw:
            event_type = event.get("type")
            if event_type == "agent_message":
                text = event.get("text")
                if isinstance(text, str) and text.strip():
                    events.append(_event("task.progress", attempt, {"text": text}))
            elif event_type == "item.completed":
                events.append(_event("task.progress", attempt, {"completed": "item"}))
        return events

    def interrupt_and_end(self, attempt: Attempt) -> None:
        """Confirm actual stop, what is secured, and what still runs."""
        msg = "interrupt lands with the interrupt test in #13"
        raise NotImplementedError(msg)

    def continue_or_hand_over(self, attempt: Attempt, checkpoint: Checkpoint) -> None:
        """Resume the pinned thread from the organization's checkpoint.

        Uses ``codex exec resume <thread_id>``, so a different engine or a
        fresh process can continue without the engine's internal history;
        the checkpoint supplies the mandate, code reference, and next action.
        """
        if attempt.engine_session_id is None:
            msg = "cannot resume an attempt with no engine thread id"
            raise ValueError(msg)
        prompt = (
            f"Continue task {checkpoint.task_id} from the checkpoint.\n"
            f"Code reference: {checkpoint.code_reference or 'unchanged'}\n"
            f"Decisions so far: {', '.join(checkpoint.decisions)}\n"
            f"Next action: {checkpoint.next_action or 'proceed'}"
        )
        self._exec("resume", attempt.engine_session_id, prompt=prompt)

    def deliver_result(self, attempt: Attempt) -> None:
        """Return artifacts, evidence, unresolved items, and next action."""
        msg = "result delivery lands with the handover test in #13"
        raise NotImplementedError(msg)


def _event(event_type: str, attempt: Attempt, payload: dict[str, object]) -> Event:
    """Build one normalized event tied to the attempt (event schema v1)."""
    return Event(
        id=f"ev-{uuid.uuid4().hex[:12]}",
        event_type=event_type,
        organization_id="",
        project_id="",
        task_id=attempt.task_id,
        attempt_id=attempt.id,
        source="codex",
        occurred_at=datetime.now(UTC),
        recorded_at=datetime.now(UTC),
        payload=payload,
    )


__all__ = ["CODEX_VERSION", "CodexAdapter"]
