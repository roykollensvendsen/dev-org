# ADR-DEV-006: Claude Code as the second agent engine, over its official SDK

## Status

Accepted. Decided by the project owner on 2026-11-27.

## Context

Issue #12 qualifies the second agent engine (Claude Code) against the same
`AgentAdapter` contract (section 4.1), per section 10 step 2. The pilot
repo's tests must run unchanged against both engines (A17), the same
mandate must give the same decisions (A19-A22), and Claude Code must use
the user's native subscription login without `ANTHROPIC_API_KEY` (A51).

Claude Code exposes two programmatic surfaces:

- its headless CLI (`claude -p --output-format=stream-json`,
  `--session-id`, `--resume`), which works but pushes the parsing and
  session handling onto dev-org, and whose message-injection into a live
  session is not a first-class feature;
- the official Agent SDK (`claude-agent-sdk`), which wraps the unmodified
  CLI: `ClaudeSDKClient` with a pinned session id, resume by id,
  interrupt, and transcript reads (`get_session_messages`), plus the
  cross-session messaging surface (`ListAgents`/`SendMessage`) used to
  reach a live session. This is the documented programmatic interface and
  the same one claude-voice proves against a native login.

The OpenCode adapters already established the pattern: the core knows the
`AgentAdapter` protocol, never an engine's internals.

## Options considered

- **Headless CLI only**: no new dependency, but dev-org must own JSON
  stream parsing, session pinning, resume, and message injection; the
  cross-session surface stays out of reach.
- **Official SDK**: the documented interface, matches claude-voice's proven
  path, covers the whole contract (start, message, follow, interrupt,
  resume), and the SDK wraps the unmodified CLI, so the A51 property
  (user's own login, no API key) is inherited rather than reconstructed.
  Cost: one dependency and the SDK's event model to normalize.
- **Both**: the CLI as a fallback is only justified once a gap appears; the
  contract tests against the SDK cover the surface now.

## Decision

Use the official `claude-agent-sdk` for the Claude Code adapter, with the
unmodified `claude` CLI behind it, and the same `AgentAdapter` contract as
OpenCode. The adapter pins each attempt to a session id chosen by
dev-org, resumes by that id, reads the transcript for follow-run events,
and uses cross-session messaging (ListAgents/SendMessage) to deliver a
message into a live session. Capability reporting states honestly what is
supported, emulated, or unavailable, including usage measurement shown as
unavailable (never zero) because the CLI does not expose a billable count.

## Consequences

- The core does not change: `test_agent_adapter_contract.py` and
  `test_engine_independence.py` run the same cases against OpenCode (ACP,
  HTTP) and Claude Code, proving the organization core is engine-independent
  (A17).
- A51 is verified live: the unmodified CLI runs a turn under the user's
  `claude.ai` login with no `ANTHROPIC_API_KEY`, and the adapter holds no
  credential state, so it cannot expose what it does not hold.
- The SDK is a pinned dependency (`claude-agent-sdk>=0.2.175`), registered
  with the engine version (2.1.331) per section 4.1.
- The CLI/session surface is Claude Code-specific; a future third engine
  (Codex) implements the same `AgentAdapter` contract with its own adapter,
  as section 4.1 requires.
