# ADR-DEV-007: Codex as the third agent engine, qualified early

## Status

Accepted. Decided by the project owner on 2026-11-27.

## Context

Issue #12 (step 2) qualifies Claude Code as the second engine. The
specification places Codex in step 5 ("A50 applies to Codex as the third
engine"), but the owner chose to qualify it early, while the engine
infrastructure and qualification method are fresh, so that A17 (the same
issue and mandate across engines) and the upcoming handover (#13) are
proven against three engines rather than two.

Codex exposes a headless surface (`codex exec --json` with JSONL events on
stdout, `codex exec resume <thread_id>` to continue a thread) and an
experimental app-server/proxy for remote connections. It authenticates
through the user's qualified ChatGPT plan login (A50: no
`OPENAI_API_KEY`).

## Options considered

- **Headless CLI only**: no new dependency, matches the proven OpenCode
  pattern, and the JSONL event stream is the documented headless
  interface. Message delivery into a live session uses the CLI's queue
  surface, which is not yet qualified.
- **App-server proxy**: reaches a daemonized server and remote threads,
  but is experimental and adds a long-lived process to supervise; the
  pilot's one-active-attempt scope does not need it yet.

## Decision

Use the headless `codex exec --json` surface for the Codex adapter, with
the unmodified `codex` CLI and the same `AgentAdapter` contract as the
other two engines. The adapter pins each attempt to the thread id from the
`thread.started` event and resumes by that id. Capability reporting states
honestly what is supported, emulated, or unavailable, including usage
measurement shown as unavailable (never zero).

## Consequences

- The core does not change: the contract and engine-independence tests now
  run against four adapters (OpenCode ACP/HTTP, Claude Code, Codex),
  proving engine independence across three engines (A17).
- A50 is verified live: the unmodified CLI runs a real turn with
  `OPENAI_API_KEY` removed from the environment, so only the ChatGPT login
  can have answered; the adapter holds no credential state.
- Message delivery into a live Codex session is marked unavailable until
  the queue surface is qualified; the adapter raises clearly instead of
  pretending delivery.
- The rest of step 5 (Redmine, migration, reuse, A06/A07/A09/A13/A15/
  A58/A66-A69/A71) stays in epic #16; this ADR only covers the engine
  qualification, which is why the step-5 registry entry is marked partial.
