# ADR-DEV-009: Hermes as a documented fourth engine, over ACP

## Status

Accepted. Decided by the project owner on 2026-11-27.

## Context

Issue #32 qualifies the installed Hermes agent (Nous Research,
`/home/roy/hermes-agent`, v0.21.3) as a documented engine behind the same
`AgentAdapter` contract (section 4.1). Hermes is not one of the
specification's three named engines (OpenCode, Claude Code, Codex); it is
qualified because it is installed on this machine and already speaks the
Agent Client Protocol, the same protocol the OpenCode ACP adapter uses.

The existing `OpenCodeApcAdapter` was ACP-generic in its plumbing but
hard-coded to the `opencode acp` command and to the OpenCode name, so it
could not represent Hermes honestly. Hermes runs its own ACP stdio server
(`hermes-acp`) with no subcommand, unlike OpenCode's `opencode acp`.

## Options considered

- **A separate Hermes adapter from scratch**: duplicates the whole ACP
  client surface for no benefit, since the protocol is the same.
- **Generalize the ACP adapter into one shared base**: the engine command
  and its optional ACP subcommand become parameters, and each engine is a
  thin subclass with its own honest name and pinned version. OpenCode keeps
  `opencode acp`; Hermes uses `hermes-acp` directly. This matches how
  Claude Code and Codex adapters already sit behind the same contract.

## Decision

Generalize the ACP adapter into `AcpAdapter` with `OpenCodeApcAdapter`
(`opencode acp`) and `HermesApcAdapter` (`hermes-acp`) as thin subclasses.
Each reports its own engine name and pinned version, and the shared
capability report states honestly what ACP supports (start, events,
interruption, resume) and what it does not (usage measurement, approval
flow, delegation: shown as unavailable, never zero).

## Consequences

- The core does not change: the contract and engine-independence tests now
  run against five adapters (OpenCode ACP/HTTP, Claude Code, Codex,
  Hermes).
- A live probe verifies Hermes answers a real turn through its own ACP
  server, and skips when the engine is not installed or reachable (as in
  CI).
- A bounded turn timeout was added to the Claude Code adapter so a hung
  engine gives up with a clear error instead of leaking a subprocess that
  locks the workspace for the next run; the live probe then skips rather
  than hangs.
- Hermes stays a documented fourth engine; the three named engines remain
  the specification's own delivery targets.
