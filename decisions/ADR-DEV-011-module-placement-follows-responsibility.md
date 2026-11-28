# ADR-DEV-011: Module placement follows responsibility, not issue grouping

## Status

Accepted. Decided by the project owner on 2026-11-28.

## Context

During issue #62 the A2A adapter was first written into
`src/dev_org/core/extensions.py`, next to the extension lifecycle. The two
shared one issue and one PR, and both concern things entering the
organization from outside, so they were placed together. A review caught
the error: an adapter that talks to something outside the core belongs
with the other adapters (gateway/ for external side effects, agents/ for
engines), not in core/, which holds lifecycle and policy services.

The placement was wrong, but the *reasoning* that produced it recurs. Code
gets put in a module because it shares an issue, a PR, or a delivery
deadline with something else there, rather than because it shares the
module's responsibility. That is delivery convenience dressed as an
architecture decision.

A correction that exists only as a code review is carried in one person's
memory. The guard `tests/test_architecture.py` now makes the concrete case
a failing test, but the principle underneath deserves to be a standing
rule that any future contributor reads, because it applies to far more
than "adapter ends in Adapter in core/".

## Options considered

- **No record; rely on the guard test.** The guard prevents the specific
  A2A-in-core shape, but not the general mistake (placement by issue
  grouping), which appears under many names. A test cannot reason about
  intention that has no mechanical signature.
- **A new skill.** Skills are human-reading guidance, but the rule is
  small and already partly mechanical (the guard). A skill would duplicate
  the guard instead of adding guidance around it.
- **A decision record.** One place states the principle, points at the
  guard as its mechanism, and is visible to every reviewer reading the
  architecture. Chosen.

## Decision

Module placement follows a module's responsibility, never the issue, PR,
or delivery group that the code arrived in. Code that talks to something
outside the core belongs with the adapters; code that governs lifecycle or
policy belongs with the core. The guard test is the mechanism; this record
is the rule. When a reviewer or a guard flags a placement, the fix is to
move the code, not to change the guard.

## Consequences

- The principle applies to every future contribution, not only the adapter
  case the guard can name.
- A reviewer now has a documented basis for rejecting a placement, so the
  objection is a rule to follow rather than a personal preference.
- Overhead is one short record and one line in the decision index; it does
  not grow a new skill or process.
- What gets worse: the rule is put in words, so a subsequent decision can
  deviate from it consciously and supersede it with its own record, rather
  than quietly ignoring an unstated habit.

## Related

- `decisions/ADR-DEV-001-small-integrable-changes.md` (temporary interface
  ownership — the companion rule to responsibility-based placement).
- `src/dev_org/core/extensions.py` and `src/dev_org/gateway/a2a.py` (the
  error this record names).
- `tests/test_architecture.py` (the guard that makes the concrete case
  a failing test).
