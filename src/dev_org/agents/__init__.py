"""Agent adapter module: the engine-independent contract for an agent engine.

The contract is fixed by the specification (section 4.1) and lives in
``protocol.py``. Issue #8 adds the first two implementations: the OpenCode
ACP adapter (primary) and the OpenCode HTTP adapter (fallback), per
ADR-DEV-005. The core knows the protocol, never an engine's internal
protocol.
"""

from dev_org.agents.acp_adapter import OpenCodeApcAdapter
from dev_org.agents.http_adapter import OpenCodeHttpAdapter
from dev_org.agents.protocol import AgentAdapter, Capabilities

__all__ = ["AgentAdapter", "Capabilities", "OpenCodeApcAdapter", "OpenCodeHttpAdapter"]
