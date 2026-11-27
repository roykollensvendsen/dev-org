# ADR-DEV-005: OpenCode adapter over ACP with an HTTP fallback

## Status

Accepted. Decided by the project owner on 2026-11-27.

## Context

Issue #8 connects the first real agent engine (OpenCode) to the common
worker contract (section 4.1). OpenCode exposes two programmatic surfaces:
the Agent Client Protocol (ACP), a standardized agent-client protocol with
an official Python SDK, and its own HTTP API (`session.create`,
`message.create`, `session.export/import`), reachable through a running
background service.

The common `AgentAdapter` port already exists (issue #4). The question is
which transport the first implementation uses, and whether a single
implementation is enough.

## Options considered

- ACP only: standard and engine-independent (Codex and other agents can
  implement the same protocol), covers the whole contract (session/new,
  prompt, update, cancel, close, resume/load, list), ships an official
  Python SDK. But OpenCode's ACP support for resume/load is not yet
  verified in practice.
- OpenCode HTTP API only: verified working on this machine, but
  OpenCode-specific, so a Codex adapter would have to be written from
  scratch.
- Both, behind the same port: one contract-test suite run against two
  implementations. Proves the port is real (section 3.4: an abstraction
  needs two real or simulated users), gives a fallback immediately, and
  keeps the core independent of either transport.

## Decision

Implement both adapters behind the existing `AgentAdapter` port:

- `OpenCodeApcAdapter` speaks ACP over stdio as the primary adapter.
- `OpenCodeHttpAdapter` speaks OpenCode's HTTP API as the fallback.
- One contract-test suite (`test_agent_adapter_contract.py`) runs the same
  cases against both, so the port is proven by two implementations and
  neither transport can drift from the contract.

The full pilot flow (task to checkpoint to result) runs against the
primary ACP adapter in issue #8; the HTTP adapter is verified with the
same contract suite, bounding model cost.

## Consequences

- The core, lifecycle, and policy modules stay independent of the
  transport: only the two adapter classes know that ACP or HTTP exists.
- Adding a future engine (Claude Code, Codex) means another class behind
  the same port, not a rewrite.
- ACP-specific gaps found during qualification can be covered by the HTTP
  adapter without changing the contract or the core.
- Two adapters to maintain, but both are thin over the same protocol, and
  the shared contract suite keeps them honest.

## Related

- [System specification, section 4.1](../dev-org-specification.md)
- [System specification, section 3.4](../dev-org-specification.md)
- [Agent Client Protocol](https://agentclientprotocol.com/)
- [OpenCode](https://opencode.ai)
