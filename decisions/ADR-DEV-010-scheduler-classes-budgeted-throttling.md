# ADR-DEV-010: Scheduler classes and budgeted throttling, after the Linux kernel

## Status

Accepted. Decided by the project owner on 2026-11-27.

## Context

Issue #35 (step 3) introduces a separate improvement budget and candidate
queue: self-improvement must never block ordinary higher-priority work
(specification section 9.2), a candidate is paused before it uses reserved
production capacity (A48), and the agents go idle without a suitable
candidate (A16). This is the first time dev-org has two kinds of work that
compete for the same workers, so the queue needs a defined scheduling
model rather than a single ordered list.

The Linux kernel solves the same problem with a hierarchy of scheduler
classes: a fixed, compiled-in priority order (`dl` -> `rt` -> `fair` ->
`idle`) in which a runnable task in a higher class always preempts a lower
one; within the `fair` class, CFS picks the task with the least virtual
runtime (`vruntime`), weighted by priority; and `cfs_bandwidth` gives a
group a quota ("max X per period Y") that throttles the group once spent,
without letting it take capacity from others. Its design deliberately does
not make the scheduler swappable per task at runtime — the class order is
fixed and the parameters are tunable.

## Options considered

- **One flat queue with priority only**: simplest, but cannot express
  "improvement work yields to any production work" as a class rule, and
  gives no budgeted throttling for the candidate.
- **A swappable scheduler port**: a `SchedulerPort` with pluggable
  implementations. Rejected because the specification's section 3.3 lists
  the outbound ports explicitly and the scheduler is not among them; new
  abstractions require at least two real or simulated users (section 3.3),
  and there is one scheduler in the MVP. It also contradicts the kernel's
  own lesson: the class hierarchy is fixed, the parameters are tunable.
- **The Linux-kernel model as an internal module**: a fixed hierarchy of
  scheduler classes (production -> improvement -> idle), a `vruntime`-like
  ordering weighted by priority within a class, and a budgeted throttle for
  the improvement class. The scheduler is an internal module with a clear
  contract, tunable per section 9.2, and only lifted to a port when a
  second real user exists.

## Decision

Adopt the Linux-kernel scheduler model as an internal module for the MVP:

- **Scheduler classes.** A fixed hierarchy `production > improvement >
  idle`. A ready production task is always picked before an improvement
  candidate; both before idle. An empty queue and no candidate means idle
  (A16).
- **Weighted ordering within a class.** Within production, ready tasks are
  ordered by priority weight (P0 > P1 > P2, stable on insertion) using the
  existing `ready_tasks` ordering; this is the `vruntime`-like rule kept
  deliberately simple for one node. Priority inheritance (A03) flows
  through the dependency chain by carrying the ordering weight.
- **Budgeted throttling for improvement.** The improvement candidate runs
  in its own budgeted capacity: a quota of active-model time and attempts
  per period. Once spent, the candidate is throttled (paused) and cannot
  take reserved production capacity (A48). Without a suitable candidate,
  the improvement class contributes nothing and the agents go idle (A16).
- **Not a port.** The scheduler is an internal module (`core/scheduler`)
  with a deterministic contract and simulated counterparts in tests. It
  becomes a port only when a second real or simulated user (a second
  project, node, or provider) needs different rules, per section 3.3.

## Consequences

- The core's `next_ready` behaviour is replaced by a scheduler that first
  consults the production class, then the improvement class, then idle.
- The improvement budget is a first-class concept: a candidate's quota is
  tracked per period and enforced by throttling, so A48 is testable
  deterministically with a simulated clock.
- Priority weights stay observable and tunable within section 9.2's frame,
  matching the kernel's "fixed hierarchy, tunable parameters" model.
- No new abstraction is created without a consumer: the scheduler module
  has one real user (the MVP queue) and is documented as the future seam
  for a port when a second user appears.
