"""Agent adapter module: the engine-independent contract for an agent engine.

The contract is fixed by the specification (section 4.1) and lives in
``protocol.py``. Issue #8 adds the first two implementations: the OpenCode
ACP adapter (primary) and the OpenCode HTTP adapter (fallback), per
ADR-DEV-005. Issue #12 adds the Claude Code adapter behind the same
contract (section 10 step 2), its early step-5 delivery adds the Codex
adapter, and issue #32 adds Hermes over ACP as a documented fourth engine.
The core knows the protocol, never an engine's internal protocol.
"""

from dev_org.agents.acp_adapter import (
    HERMES_VERSION,
    OPENCODE_VERSION,
    AcpAdapter,
    HermesApcAdapter,
    OpenCodeApcAdapter,
)
from dev_org.agents.claude_code import CLAUDE_CODE_VERSION, ClaudeCodeAdapter
from dev_org.agents.codex_adapter import CODEX_VERSION, CodexAdapter
from dev_org.agents.http_adapter import OpenCodeHttpAdapter
from dev_org.agents.protocol import AgentAdapter, Capabilities

__all__ = [
    "CLAUDE_CODE_VERSION",
    "CODEX_VERSION",
    "HERMES_VERSION",
    "OPENCODE_VERSION",
    "AcpAdapter",
    "AgentAdapter",
    "Capabilities",
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "HermesApcAdapter",
    "OpenCodeApcAdapter",
    "OpenCodeHttpAdapter",
]
