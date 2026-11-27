# ADR-DEV-008: Handover goes through the organization's checkpoint

## Status

Accepted. Decided by the project owner on 2026-11-27.

## Context

Issue #13 (step 2) requires that another engine can continue an issue that
has secured code and waits on CI, without double external actions
(acceptance test A18). The specification's section 4.1 gives the engine
contract a `continue or hand over` operation that must either resume the
engine's session where supported or start a new attempt from the
organization's checkpoint, stating which method is used. Section 5's
Waiting state stores the wait condition, last verified progress,
branch/commit, and next action.

The three qualified engines each expose resume by their own session/thread
id, but that id is engine-internal: it must not be the organization's
record of where work stands. The checkpoint (`state/models.py`) already
carries code reference, test evidence, decisions, unresolved items, wait
conditions, and next action, engine-independently.

## Options considered

- **Resume the old engine's session directly on handover**: cheapest when
  the same engine stays, but carries engine history across the boundary
  and is meaningless when switching to a different engine.
- **Continue from the organization's checkpoint, always**: the checkpoint
  is engine-independent by construction, so the same code path serves both
  an engine-internal resume and a true engine switch. A complete checkpoint
  is required, so nothing is lost in the transfer.

## Decision

Handover always goes through the organization's checkpoint. `HandoverService`
wakes the waiting task (A18's scenario), creates one new attempt, refuses an
incomplete checkpoint, and calls the new engine's `continue_or_hand_over`
with the checkpoint. A stable idempotency key makes a duplicate handover one
logical continuation. Messages and approval answers go through `MessageInbox`
with stable ids and separate received/processed state, per section 8.3.

## Consequences

- The engine's internal session id stays a runtime reference on the
  attempt; it is never the organization's record of progress.
- An engine change alone orders no build: the gateway re-finds the existing
  PR (A18) and reconciles lost external answers via the journal (A36).
- A duplicate handover, a duplicate message, or an expired approval answer
  grants no new continuation (A23, A35, A54).
- The same `continue_or_hand_over` code path serves same-engine resume and
  cross-engine handover, so no core branch depends on which engine is
  switching.
