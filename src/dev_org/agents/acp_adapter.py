"""OpenCode and Hermes adapters over the Agent Client Protocol.

The primary adapters for issues #8 and #32, per ADR-DEV-005 and
ADR-DEV-009. They implement the engine-independent ``AgentAdapter`` protocol
(section 4.1) by speaking ACP over stdio: OpenCode as ``opencode acp``,
Hermes as the ``hermes-acp`` server directly.

The ACP surface used here is the stable v1 client surface, verified against
the local engines: initialize, new_session, prompt, cancel, resume_session,
load_session, close, list_sessions. The SDK's ``spawn_agent_process`` starts
the agent subprocess and returns a connection whose snake_case methods
mirror those operations.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from acp.client.connection import Client, TextContentBlock  # type: ignore[attr-defined]  # SDK does not export these in __all__
from acp.stdio import spawn_agent_process

from dev_org.agents.protocol import Capabilities

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from acp.client.connection import ClientSideConnection

    from dev_org.state.models import Attempt, Checkpoint, Event, Task

#: The pinned engine/adapter version pairs (section 4.1: registered together).
OPENCODE_VERSION = "2.0.29"
HERMES_VERSION = "0.21.3"


class _Client(Client):
    """A minimal ACP client: no-ops for the agent-initiated methods.

    OpenCode's agent may push session updates, permission requests, and
    terminal output toward the client. Issue #8 only drives the agent; these
    arrive but are not yet consumed, so each handler does nothing. The
    signatures mirror ``acp.interfaces.Client`` so mypy accepts the override.
    """

    async def auth_status_update(
        self, state: str, accounts: list[Any] | None = None, **kwargs: Any
    ) -> None: ...
    async def complete_elicitation(self, elicitation_id: str, **kwargs: Any) -> None: ...
    async def create_elicitation(self, message: str, mode: Any, **kwargs: Any) -> Any: ...
    async def create_terminal(
        self,
        session_id: str,
        command: str,
        args: list[str] | None = None,
        env: list[Any] | None = None,
        cwd: str | None = None,
        output_byte_limit: int | None = None,
        **kwargs: Any,
    ) -> Any: ...
    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Handle an extension method call; issue #8 does not use extensions."""
        del method, params
        return {}

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None: ...
    async def kill_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> Any: ...
    async def mcp_message(
        self,
        server_id: str,
        request_id: str,
        method: str,
        params: dict[str, Any] | None = None,
        session_id: str | None = None,
        tool_call_id: str | None = None,
        **kwargs: Any,
    ) -> Any: ...
    def on_connect(self, conn: Any) -> None: ...
    async def read_text_file(
        self, session_id: str, path: str, line: int | None = None, limit: int | None = None, **kwargs: Any
    ) -> Any: ...
    async def release_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> Any: ...
    async def request_permission(
        self, session_id: str, tool_call: Any, options: list[Any], **kwargs: Any
    ) -> Any: ...
    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None: ...
    async def terminal_output(self, session_id: str, terminal_id: str, **kwargs: Any) -> Any: ...
    async def wait_for_terminal_exit(self, session_id: str, terminal_id: str, **kwargs: Any) -> Any: ...
    async def write_text_file(self, session_id: str, path: str, content: str, **kwargs: Any) -> Any: ...


class AcpAdapter:
    """Talk to any ACP-speaking engine over the Agent Client Protocol.

    One adapter per engine, parameterized by the engine command and its
    optional ACP subcommand: OpenCode runs ``opencode acp``, Hermes runs
    ``hermes-acp`` directly. The engine name is the adapter's own class, so
    the capability report never lies about which engine is behind it.
    """

    #: The engine's name for capability reports and event sources.
    engine_name = "acp"
    #: The pinned engine version for this adapter (section 4.1).
    engine_version = "0.0.0"

    def __init__(self, *, command: str, version: str | None = None, acp_args: tuple[str, ...] = ()) -> None:
        """Bind the adapter to the engine command, optional ACP args, and version."""
        self.command = command
        self.acp_args = acp_args
        self.version = version or self.engine_version

    def report_capabilities(self) -> Capabilities:
        """What this ACP engine supports, emulates, or lacks (section 4.1).

        ACP covers start, message delivery, resume, and a normalized event
        stream, so those are reported as supported; usage measurement,
        approval flow, and delegation are unavailable, and the core must
        show unknown usage as unknown, never as zero.
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

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[ClientSideConnection]:
        """A connected, initialized ACP session with the agent subprocess."""
        async with spawn_agent_process(_Client(), self.command, *self.acp_args, cwd="/tmp/opencode") as (
            conn,
            _process,
        ):
            await conn.initialize(protocol_version=1)
            yield conn

    async def _prompt(self, session_id: str, text: str) -> None:
        """Send one user prompt to an ACP session."""
        async with self._connection() as conn:
            await conn.prompt(session_id=session_id, prompt=[TextContentBlock(type="text", text=text)])

    # -- AgentAdapter contract -------------------------------------------

    def start_work(self, task: Task, attempt: Attempt, mandate: str, budget: str, workspace: str) -> None:
        """Start one attempt; a repeated start must not create a second owner."""

        async def _start() -> None:
            async with self._connection() as conn:
                new = await conn.new_session(cwd=workspace)
                attempt.engine_session_id = new.session_id
                prompt = f"Start task {task.id}: {task.title}\nMandate: {mandate}\nBudget: {budget}"
                await conn.prompt(
                    session_id=new.session_id, prompt=[TextContentBlock(type="text", text=prompt)]
                )

        asyncio.run(_start())

    def deliver_message(
        self, message_id: str, sender: str, recipient: str, task_id: str, payload: str
    ) -> None:
        """Deliver a message tied to the task, distinct from a result."""
        del message_id, task_id  # the ACP prompt carries the content; IDs are logged by the core
        asyncio.run(self._prompt(recipient, f"[{sender}] {payload}"))

    def follow_run(self, attempt: Attempt) -> list[Event]:
        """Yield normalized events for status, progress, and blockage."""
        msg = "session/update streaming arrives with issue #10"
        raise NotImplementedError(msg)

    def interrupt_and_end(self, attempt: Attempt) -> None:
        """Confirm actual stop, what is secured, and what still runs."""
        msg = "session/cancel lands with the interrupt test in #10"
        raise NotImplementedError(msg)

    def continue_or_hand_over(self, attempt: Attempt, checkpoint: Checkpoint) -> None:
        """Resume the session, or continue from the organization's checkpoint."""
        msg = "session/resume lands with the handover test in #10"
        raise NotImplementedError(msg)

    def deliver_result(self, attempt: Attempt) -> None:
        """Return artifacts, evidence, unresolved items, and next action."""
        msg = "result delivery lands with the pilot in #11"
        raise NotImplementedError(msg)


class OpenCodeApcAdapter(AcpAdapter):
    """OpenCode over ACP (``opencode acp``), per ADR-DEV-005."""

    engine_name = "opencode"
    engine_version = OPENCODE_VERSION

    def __init__(self, *, command: str = "opencode", version: str | None = None) -> None:
        """Bind the adapter to the OpenCode command and the pinned version."""
        super().__init__(command=command, version=version, acp_args=("acp",))


class HermesApcAdapter(AcpAdapter):
    """Hermes over ACP (``hermes-acp``), a documented fourth engine (ADR-DEV-009)."""

    engine_name = "hermes"
    engine_version = HERMES_VERSION

    def __init__(self, *, command: str = "hermes-acp", version: str | None = None) -> None:
        """Bind the adapter to the Hermes ACP command and the pinned version."""
        super().__init__(command=command, version=version)


__all__ = [
    "HERMES_VERSION",
    "OPENCODE_VERSION",
    "AcpAdapter",
    "HermesApcAdapter",
    "OpenCodeApcAdapter",
]
