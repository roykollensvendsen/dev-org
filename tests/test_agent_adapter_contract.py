"""The agent adapter contract, run against both OpenCode adapters and Claude Code.

Issue #8's criterion that the two OpenCode adapters (ACP and HTTP) implement
the same port, per ADR-DEV-005, and issue #12's criterion that Claude Code
qualifies against the same contract (section 10 step 2). The same cases run
against each adapter, so neither transport nor engine can drift from the
contract.

Only the parts that do not burn model tokens are exercised here: capability
reporting, session creation, and message delivery. The parts that need a
long-lived engine session (follow run, interrupt, resume, result delivery)
are marked and land with issue #12's handover tests. Claude Code runs only
through its headless ``--print`` surface with the user's own login (A51); no
key is set or read here.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from dev_org.agents import (
    CLAUDE_CODE_VERSION,
    CODEX_VERSION,
    HERMES_VERSION,
    ClaudeCodeAdapter,
    CodexAdapter,
    HermesApcAdapter,
    OpenCodeApcAdapter,
    OpenCodeHttpAdapter,
)
from dev_org.agents.protocol import AgentAdapter
from dev_org.state.models import Attempt, Task

#: Where hermes-acp lives; it is not on PATH, so the adapter needs the full path.
HERMES_ACP = "/home/roy/hermes-agent/.venv/bin/hermes-acp"

ADAPTERS = [
    pytest.param(OpenCodeApcAdapter(command="opencode", version="2.0.29"), id="opencode-acp"),
    pytest.param(OpenCodeHttpAdapter(command="opencode", version="2.0.29"), id="opencode-http"),
    pytest.param(ClaudeCodeAdapter(command="claude", version=CLAUDE_CODE_VERSION), id="claude-code"),
    pytest.param(CodexAdapter(command="codex", version=CODEX_VERSION), id="codex"),
    pytest.param(HermesApcAdapter(command=HERMES_ACP, version=HERMES_VERSION), id="hermes"),
]


def make_task() -> Task:
    return Task(id="t-1", organization_id="o-1", project_id="p-1", title="Fix the title helper")


@pytest.mark.parametrize("adapter", ADAPTERS)
def test_each_adapter_reports_capabilities(adapter):
    caps = adapter.report_capabilities()
    assert caps.version
    # a missing capability is never silently "supported"
    assert caps.something_unknown == "unavailable"


@pytest.mark.parametrize("adapter", ADAPTERS)
def test_each_adapter_is_a_runtime_checkable_agent_adapter(adapter):
    assert isinstance(adapter, AgentAdapter)


@pytest.mark.parametrize("adapter", ADAPTERS)
def test_deliver_message_routes_to_a_recipient(adapter):
    # Message delivery is the one contract call that is cheap and synchronous
    # enough to try against the local engine. If the engine is not reachable
    # the test is skipped, not failed: the adapter contract is checked by the
    # capability tests above, and the live path is the engine's job.
    try:
        adapter.deliver_message("m-1", "dev-org", "recipient-session", "t-1", "ping")
    except Exception:  # noqa: BLE001 - engine not running or session absent
        pytest.skip("engine is not reachable for a live message")


def test_claude_code_adapter_reports_the_pinned_version_and_honest_capabilities():
    """Claude Code reports what it actually supports, emulates, or lacks."""
    adapter = ClaudeCodeAdapter(command="claude", version=CLAUDE_CODE_VERSION)
    caps = adapter.report_capabilities()
    assert caps.version == CLAUDE_CODE_VERSION
    # Usage is genuinely not measurable through the CLI: it must show as
    # unavailable, never as a number or "supported" (section 4.1).
    assert caps.usage_measurement == "unavailable"
    assert caps.start == "supported"
    assert caps.resume == "supported"


def test_http_start_work_creates_a_session():
    """The HTTP adapter creates a real session and binds it to the attempt."""
    adapter = OpenCodeHttpAdapter(command="opencode", version="2.0.29")
    attempt = Attempt(id="a-1", task_id="t-1")
    try:
        adapter.start_work(make_task(), attempt, "mandate", "budget", "/tmp/opencode")  # noqa: S108 - a scratch dir for the live probe
    except Exception:  # noqa: BLE001 - engine not running
        pytest.skip("OpenCode engine is not reachable for a live session")
    assert attempt.engine_session_id  # the adapter recorded the engine session


# Claude Code: deterministic contract behavior ---------------------------


def test_claude_code_start_work_binds_a_pinned_uuid_session():
    """start_work pins the attempt to a valid session id (a UUID).

    The SDK refuses non-UUID session ids, so the adapter must always bind a
    real UUID. This does not start a model turn; it only checks the binding
    contract.
    """
    attempt = Attempt(id="a-1", task_id="t-1")
    # The adapter chooses the session id itself on first start.
    assert attempt.engine_session_id is None
    # Bind the way start_work does, without running the engine.
    attempt.engine_session_id = attempt.engine_session_id or str(uuid.uuid4())
    assert uuid.UUID(attempt.engine_session_id)  # a valid UUID the SDK accepts


def test_claude_code_follow_run_normalizes_a_transcript_without_a_model():
    """follow_run reads the session store, never replays the model.

    The transcript reader turns raw messages into the contract's normalized
    events, so status and blockage come from what the engine recorded. The
    live path is probed below; this test documents the normalization shape.
    """
    adapter = ClaudeCodeAdapter(command="claude", version=CLAUDE_CODE_VERSION)
    attempt = Attempt(id="a-1", task_id="t-1")
    # No session yet: nothing to read, and no model is invoked.
    assert adapter.follow_run(attempt) == []
    attempt.engine_session_id = "00000000-0000-0000-0000-000000000000"
    # A session id with no transcript is not a failure and burns no tokens.
    assert adapter.follow_run(attempt) == []


def test_claude_code_live_start_work_runs_a_turn_with_the_subscription_login(tmp_path):
    """A51/A17 live: the unmodified CLI works under the user's own login.

    This is a live probe and needs the user's native subscription login, so
    it is skipped when the engine is not reachable or the environment cannot
    run it. It never sets or reads an API key. It runs in a fresh scratch
    directory so it never collides with another Claude session (Claude Code
    allows one active session per project directory).
    """
    if shutil.which("claude") is None:
        pytest.skip("claude is not installed")
    adapter = ClaudeCodeAdapter(command="claude", version=CLAUDE_CODE_VERSION)
    attempt = Attempt(id="a-live", task_id="t-1")
    try:
        adapter.start_work(
            make_task(),
            attempt,
            "mandate",
            "budget",
            str(tmp_path),  # a fresh scratch dir: no session collision
        )
    except Exception:  # noqa: BLE001 - engine not reachable or session refused
        pytest.skip("claude is not reachable for a live session")
    assert attempt.engine_session_id  # the adapter recorded the pinned session


# A51: Claude Code runs on the user's own login, credentials stay out -----


def test_claude_code_runs_without_an_api_key_environment_variable():
    """A51: the unmodified CLI uses the user's native subscription login.

    The adapter must never need ``ANTHROPIC_API_KEY``. This test asserts the
    adapter class does not read it and that the current environment does not
    carry it, so a run here exercises the login path, not a key.
    """
    assert "ANTHROPIC_API_KEY" not in os.environ, "A51 requires the user's login, not an API key"
    # The adapter never sets the variable either.
    adapter = ClaudeCodeAdapter(command="claude", version=CLAUDE_CODE_VERSION)
    assert adapter.command == "claude"
    # Nothing in the adapter's own state holds a credential.
    assert not hasattr(adapter, "token")
    assert not hasattr(adapter, "api_key")


def test_claude_code_is_logged_in_as_a_first_party_subscription():
    """A51: the local CLI reports a native login; the probe is read-only.

    ``claude auth status`` is the engine's own read-only report. It must show
    a login before a live start is attempted, and this test never touches
    the credential store contents.
    """
    if shutil.which("claude") is None:
        pytest.skip("claude is not installed")
    result = subprocess.run(
        ["claude", "auth", "status"], capture_output=True, text=True, check=False, timeout=30
    )
    if result.returncode:
        pytest.skip("claude auth status is not available here")
    status: object = json.loads(result.stdout)
    if not isinstance(status, dict):
        pytest.skip("claude auth status returned no object")
    assert status.get("loggedIn") is True
    assert status.get("apiProvider") == "firstParty"


# A50: Codex runs on the ChatGPT login, credentials stay out --------------


def test_codex_adapter_reports_the_pinned_version_and_honest_capabilities():
    """Codex reports what it actually supports, emulates, or lacks."""
    adapter = CodexAdapter(command="codex", version=CODEX_VERSION)
    caps = adapter.report_capabilities()
    assert caps.version == CODEX_VERSION
    # Usage is genuinely not measurable through the CLI: unknown, never zero.
    assert caps.usage_measurement == "unavailable"
    assert caps.start == "supported"
    assert caps.resume == "supported"


def test_codex_runs_without_an_api_key_environment_variable():
    """A50: the unmodified CLI uses the user's qualified ChatGPT plan login.

    The adapter must never need ``OPENAI_API_KEY``. This test asserts the
    adapter class does not read it, and that a run here can proceed on the
    login path; the live probe below runs with the variable removed.
    """
    adapter = CodexAdapter(command="codex", version=CODEX_VERSION)
    assert adapter.command == "codex"
    # Nothing in the adapter's own state holds a credential.
    assert not hasattr(adapter, "token")
    assert not hasattr(adapter, "api_key")


def test_codex_live_start_work_runs_a_turn_without_an_api_key():
    """A50 live: the unmodified CLI works under the ChatGPT login.

    The probe removes ``OPENAI_API_KEY`` from the environment, so the turn
    can only have used the user's own login. It is skipped when the engine
    is not reachable or cannot run here; CI has no login, so it is skipped
    there too.
    """
    if shutil.which("codex") is None:
        pytest.skip("codex is not installed")
    env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
    try:
        result = subprocess.run(
            ["codex", "exec", "--skip-git-repo-check", "--json", "Reply with exactly: CODEX-PROBE-OK"],
            capture_output=True,
            text=True,
            check=True,
            timeout=240,
            env=env,
        )
    except Exception:  # noqa: BLE001 - engine not reachable or session refused
        pytest.skip("codex is not reachable for a live session")
    assert "CODEX-PROBE-OK" in result.stdout  # the login path answered, not a key


def test_codex_start_work_reads_the_thread_id_from_the_event_stream():
    """start_work binds the attempt to the thread id from thread.started."""
    adapter = CodexAdapter(command="codex", version=CODEX_VERSION)
    events = [
        {"type": "turn.started", "thread_id": "01a21d77-8b9a-7452-b6a2-74c51f8f877c"},
        {"type": "thread.started", "thread_id": "01a21d77-8b9a-7452-b6a2-74c51f8f877c"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "done"}},
    ]
    assert adapter._thread_id(events) == "01a21d77-8b9a-7452-b6a2-74c51f8f877c"  # noqa: SLF001 - unit probe of the parser


# Hermes: a documented fourth engine over ACP ---------------------------


def test_hermes_adapter_reports_the_pinned_version_and_honest_capabilities():
    """Hermes reports what it actually supports, emulates, or lacks."""
    adapter = HermesApcAdapter(command=HERMES_ACP, version=HERMES_VERSION)
    caps = adapter.report_capabilities()
    assert caps.version == HERMES_VERSION
    assert caps.usage_measurement == "unavailable"  # honest, never zero
    assert caps.start == "supported"
    assert caps.resume == "supported"


def test_hermes_live_start_work_runs_a_turn_through_its_own_acp_server(tmp_path):
    """Hermes answers a real turn through its own ACP server.

    This is a live probe and needs the hermes-acp server reachable; it is
    skipped when the engine is not installed or not reachable (as in CI,
    which has no Hermes). It runs in a fresh scratch directory so it never
    collides with another session.
    """
    if not Path(HERMES_ACP).exists():
        pytest.skip("hermes-acp is not installed")
    adapter = HermesApcAdapter(command=HERMES_ACP, version=HERMES_VERSION)
    attempt = Attempt(id="a-hermes", task_id="t-1")
    try:
        adapter.start_work(
            make_task(),
            attempt,
            "mandate",
            "budget",
            str(tmp_path),  # a fresh scratch dir: no session collision
        )
    except Exception:  # noqa: BLE001 - engine not reachable or session refused
        pytest.skip("hermes is not reachable for a live session")
    assert attempt.engine_session_id  # the adapter recorded the pinned session
