# ADR-DEV-003: Use OpenCode as the first agent engine

## Status

Accepted. Decided by the project owner on 2026-11-26.

## Context

The specification's MVP decisions (section 10.2) named Codex App Server as
the first agent adapter, Claude Code as the second, and OpenCode as the
third. The pilot runs on this machine, where the Claude Code subscription
is exhausted and cannot be relied on for the first delivery, and where
OpenCode is already installed and authenticated. The first adapter must be
one the pilot can actually qualify.

OpenCode authenticates differently from Codex and Claude Code: it is an
open-source CLI that calls provider APIs (on this machine: chutes,
openrouter, and anthropic) rather than a vendor subscription login. The
specification's subscription-login section described only the vendor
login model, so adopting OpenCode as the first engine requires stating how
its provider-API authentication is treated.

## Options considered

- Keep Codex App Server as the first engine: matches the original text,
  but requires a ChatGPT/Codex plan login whose availability on this
  machine is not established, and does not address the exhausted Claude
  subscription behind the change request.
- Use OpenCode as the first engine with provider-API authentication: the
  engine is already installed and authenticated on the pilot machine, and
  provider APIs are a documented, supported authentication model. Claude
  Code moves to second and Codex to third, so the remaining two engines
  still cover the subscription-login model.
- Defer the decision: leaves the specification claiming a first engine the
  pilot cannot necessarily qualify, and blocks the first adapter work.

## Decision

OpenCode is the first agent adapter, in step 1 of the delivery order.
Claude Code is the second engine, in step 2; Codex App Server is the third
engine, in step 5. OpenCode authenticates through its configured provider
APIs rather than a vendor subscription login; the specification describes
that model explicitly and adds an acceptance test for it (A80).

Provider credentials remain in the user's OpenCode configuration and OS
credential store; dev-org does not collect, decode, or forward them. The
same credential-isolation and quota rules apply as for subscription
logins, with provider-API keys treated as the credential to protect.

## Consequences

- The first adapter is one the pilot machine already runs, so step 1 is
  qualifiable without depending on a vendor plan login.
- The specification's subscription-login section is broadened to cover
  provider-API authentication, and a new acceptance test (A80) is added
  for it. A50, which tested the Codex plan login, moves to step 5 where
  Codex becomes the third engine.
- The engine ordering changes in sections 9, 10.2, 11, and 12; the backlog
  issues for the first engine reference OpenCode and A80 instead of Codex
  and A50.
- Codex and Claude Code adapters are still required later; nothing about
  the adapter contract changes, so their later qualification is unaffected.

## Related

- [System specification, section 10.2](../dev-org-specification.md)
- [System specification, section 11](../dev-org-specification.md)
- [System specification, section 12](../dev-org-specification.md)
