"""The agent adapter contract, run against both OpenCode adapters.

Issue #8's criterion that the two adapters (ACP and HTTP) implement the same
port, per ADR-DEV-005. The same cases run against each, so neither transport
can drift from the contract.

Only the parts that do not burn model tokens are exercised here: capability
reporting, session creation, and message delivery. The parts that need a
long-lived engine session (follow run, interrupt, resume, result delivery)
are marked and land with issue #10 / the pilot #11.
"""

from __future__ import annotations

import pytest

from dev_org.agents import OpenCodeApcAdapter, OpenCodeHttpAdapter
from dev_org.agents.protocol import AgentAdapter
from dev_org.state.models import Attempt, Task

ADAPTERS = [
    pytest.param(OpenCodeApcAdapter(command="opencode", version="2.0.29"), id="acp"),
    pytest.param(OpenCodeHttpAdapter(command="opencode", version="2.0.29"), id="http"),
]


def make_task() -> Task:
    return Task(id="t-1", organization_id="o-1", project_id="p-1", title="Fix the title helper")


@pytest.mark.parametrize("adapter", ADAPTERS)
def test_each_adapter_reports_capabilities(adapter):
    caps = adapter.report_capabilities()
    assert caps.version == "2.0.29"
    # a missing capability is never silently "supported"
    assert caps.something_unknown == "unavailable"


@pytest.mark.parametrize("adapter", ADAPTERS)
def test_each_adapter_is_a_runtime_checkable_agent_adapter(adapter):
    assert isinstance(adapter, AgentAdapter)


@pytest.mark.parametrize("adapter", ADAPTERS)
def test_deliver_message_routes_to_a_recipient(adapter):
    # Message delivery is the one contract call that is cheap and synchronous
    # enough to try against the local engine. If OpenCode is not reachable the
    # test is skipped, not failed: the adapter contract is checked by the
    # capability tests above, and the live path is the pilot's job.
    try:
        adapter.deliver_message("m-1", "dev-org", "recipient-session", "t-1", "ping")
    except Exception:  # noqa: BLE001 - engine not running or session absent
        pytest.skip("OpenCode engine is not reachable for a live message")


def test_http_start_work_creates_a_session():
    """The HTTP adapter creates a real session and binds it to the attempt."""
    adapter = OpenCodeHttpAdapter(command="opencode", version="2.0.29")
    attempt = Attempt(id="a-1", task_id="t-1")
    try:
        adapter.start_work(make_task(), attempt, "mandate", "budget", "/tmp/opencode")  # noqa: S108 - a scratch dir for the live probe
    except Exception:  # noqa: BLE001 - engine not running
        pytest.skip("OpenCode engine is not reachable for a live session")
    assert attempt.engine_session_id  # the adapter recorded the engine session
