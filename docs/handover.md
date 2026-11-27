# Handover between engines

Issue #13 (step 2) lets another engine continue from the organization's
checkpoint when an issue has secured code and waits on CI (acceptance test
A18). This page records what a handover carries, what it does not do, and
how it is checked.

## What a handover carries

`HandoverService.hand_over` hands the issue to a new engine from the
organization's checkpoint — never from the old engine's internal history.
The checkpoint must be complete before the handover is allowed:

| Field | What it preserves | Refused when |
|---|---|---|
| `code_reference` | the branch/commit the work is on | missing |
| `test_evidence` | the checks that passed | missing |
| `decisions` | the agreed choices so far | missing |
| `wait_conditions` | what the issue is waiting on | missing |
| `next_action` | what the new engine should do next | missing |

A handover creates one new attempt for the same task, wakes the task from
Waiting (A18's scenario: the issue waits on CI), and calls the new engine's
`continue_or_hand_over` with the checkpoint.

## What an engine change does not do

- **Orders no build (A18).** The existing PR is the same one the new engine
  continues towards; the gateway re-finds it rather than publishing again,
  so an engine switch alone triggers zero builds.
- **Repeats a lost external action (A36).** The operations journal is
  reconciled before any resubmission; a crash after an external action was
  sent does not repeat the side effect.
- **Starts a second continuation.** A duplicate handover of the same
  checkpoint to the same engine is one logical continuation, keyed by a
  stable idempotency key.

## Messages and approval answers

`MessageInbox` gives every message a stable `message_id` and records
delivery state separately: queued, available, received, processed,
rejected, or expired (section 8.3). A duplicate delivery is one logical
processing; a message for the wrong recipient is rejected and grants no
mandate; an expired approval answer grants nothing (A23, A35, A54). A
message never changes ownership, mandate, or authority.

## How it is checked

`tests/test_handover.py` maps one test to each acceptance criterion and the
referenced A-tests, against contract-faithful engine doubles. The real
engines (OpenCode, Claude Code, Codex) are qualified by the contract suite,
and their `continue_or_hand_over` implementations are covered there.
