# Decision records

A decision that costs more to reverse than to take is written down here before
the code that rests on it. A decision that only implements one already taken
is not; it is a commit message.

## The form

Every record is `ADR-DO-NNN-a-short-title.md`, with these sections in
this order:

| Section | Holds |
|---|---|
| Status | Accepted or Proposed, who decided, when; an objection returns it to Proposed |
| Context | what was true when the question arose, with sources where the facts are checkable |
| Options considered | every option weighed, including doing nothing, each with why it was not taken |
| Decision | what was chosen, in one paragraph |
| Consequences | what this costs, what it forecloses, and at least one thing that gets worse |
| Related | the pages it shapes |

Numbers are one sequence and never reused. A record is superseded by a later
one, never edited into a different decision.

Record the process choices too, not only the artefact ones. How a change is
made, and why, is what costs time on every future contribution, and it is the
decision nobody writes down.

## The records

| Id | Decides | Status |
|---|---|---|
| [ADR-DEV-001](ADR-DEV-001-small-integrable-changes.md) | Small changes, explicit contracts, and temporary interface ownership | Accepted |
| [ADR-DEV-002](ADR-DEV-002-network-copyleft-license.md) | AGPL-3.0-or-later to cover modified network deployments | Accepted |
| [ADR-DEV-003](ADR-DEV-003-use-opencode-first-engine.md) | Use OpenCode as the first agent engine | Accepted |
| [ADR-DEV-004](ADR-DEV-004-first-pilot-basis.md) | First pilot basis and verification definition | Accepted |
| [ADR-DEV-005](ADR-DEV-005-opencode-adapter-acp-http.md) | OpenCode adapter over ACP with an HTTP fallback | Accepted |
| [ADR-DEV-006](ADR-DEV-006-claude-code-second-engine-sdk.md) | Claude Code as the second agent engine, over its official SDK | Accepted |
| [ADR-DEV-007](ADR-DEV-007-codex-third-engine-early.md) | Codex as the third agent engine, qualified early | Accepted |
| [ADR-DEV-008](ADR-DEV-008-handover-through-checkpoint.md) | Handover goes through the organization's checkpoint | Accepted |
| [ADR-DEV-009](ADR-DEV-009-hermes-fourth-engine-acp.md) | Hermes as a documented fourth engine, over ACP | Accepted |
| [ADR-DEV-010](ADR-DEV-010-scheduler-classes-budgeted-throttling.md) | Scheduler classes and budgeted throttling, after the Linux kernel | Accepted |
| [ADR-DEV-011](ADR-DEV-011-module-placement-follows-responsibility.md) | Module placement follows responsibility, not issue grouping | Accepted |

What is deliberately left undone, and what would make each worth doing, is
[`deferred.md`](deferred.md). A thing left undone with no trigger is a thing
forgotten.
