# Agent engines: capabilities and how they are enforced

Issue #12 (step 2) qualifies Claude Code against the same `AgentAdapter`
contract (section 4.1) as OpenCode. This page records what each engine
actually supports, emulates, or lacks, as reported by the adapters, and how
a capability that is not really enforceable is kept honest. The same
information is machine-readable from `report_capabilities()` and checked by
the contract tests.

## The engines

| Engine | Adapter | Auth model (section 10.3) |
|---|---|---|
| OpenCode | `OpenCodeApcAdapter` (ACP, primary), `OpenCodeHttpAdapter` (HTTP fallback) | the user's configured provider APIs (chutes, openrouter, anthropic) |
| Claude Code | `ClaudeCodeAdapter` (official Agent SDK over the unmodified CLI) | the user's native `claude.ai` subscription login; no `ANTHROPIC_API_KEY` (A51) |
| Codex | `CodexAdapter` (unmodified CLI over `codex exec --json`) | the user's qualified ChatGPT plan login; no `OPENAI_API_KEY` (A50) |
| Hermes | `HermesApcAdapter` (ACP stdio server) | the engine's own configured provider access; a documented fourth engine (ADR-DEV-009) |

## Capability report (as enforced, not assumed)

`Capabilities` states one of `supported`, `emulated`, or `unavailable` per
capability; a missing capability leads to another qualified choice or a
concrete blockage, never a silent "supported" (section 4.1).

| Capability | OpenCode (ACP/HTTP) | Claude Code | Codex | Hermes (ACP) | Notes |
|---|---|---|---|---|---|
| start | supported | supported | supported | supported | a pinned session/thread per attempt; a repeated start cannot create a second owner |
| events (follow run) | supported (stream-json / SDK) | supported (transcript) | supported (JSONL exec events) | supported (ACP) | `follow_run` reads what the engine recorded; no model replay |
| interruption | supported | supported (SDK `interrupt`) | supported (CLI stop) | supported (ACP) | a received interrupt is not a confirmed termination; the adapter reports the stop |
| resume | supported | supported (SDK `resume` by session id) | supported (`codex exec resume <thread_id>`) | supported (ACP) | the conversation lives in the engine's own session store |
| approval flow | unavailable | unavailable | unavailable | unavailable | policy and the gateway decide approvals, not the engine (section 3.2) |
| delegation | unavailable | unavailable | unavailable | unavailable | internal subagents stay within the same mandate; organization tasks go through dev-org |
| usage measurement | unavailable | unavailable | unavailable | unavailable | the CLI exposes no billable count, so usage is shown as unknown, never as zero |

## How each claim is enforced

- **The same contract runs against every engine.** `test_agent_adapter_contract.py`
  parametrizes the capability, protocol-conformance, and message-delivery
  cases over all three adapters; `test_engine_independence.py` drives the
  same pilot-workflow line and the same mandate through each (A17,
  A19-A22).
- **A missing capability is never claimed as supported.** The contract test
  asserts `caps.something_unknown == "unavailable"`, so a capability that
  does not exist cannot be reported as present.
- **Usage is honest.** Every adapter reports `usage_measurement =
  "unavailable"`; the core must show unknown usage as unknown, per section
  4.1. A hard usage cap only starts work when the chosen combination can
  enforce it or an approved conservative limit applies.
- **Claude Code's A51 property is verified live.** The contract suite's
  live test runs a real turn under the native login (it skips when the
  engine is not reachable), asserts the environment carries no
  `ANTHROPIC_API_KEY`, and asserts the adapter holds no credential state.
- **Codex's A50 property is verified live.** The contract suite's live test
  removes `OPENAI_API_KEY` from the environment and runs a real turn, so
  only the ChatGPT plan login can have answered; it skips when the engine
  is not reachable or has no login (as in CI).
- **Hermes answers through its own ACP server.** The contract suite's live
  probe starts a real turn through the `hermes-acp` server and skips when
  the engine is not installed or reachable (as in CI).

## What is still live, and where it runs

- A real end-to-end delivery with each engine (A17's full loop) is the
  handover's job (#13) and runs against the qualified engine where it is
  installed; the deterministic contract and engine-independence tests run
  in CI.
- Codex message delivery into a live session uses the CLI's queue surface,
  which is not yet qualified; the adapter raises clearly rather than
  pretending a message was delivered.
- Rootless Podman sandbox probes (A20/A40) are `live`-marked and run where
  `podman` is installed, as in the step-1 registry.
