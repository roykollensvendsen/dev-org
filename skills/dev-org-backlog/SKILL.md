---
name: dev-org-backlog
description: Manage dev-org's backlog and epics as board-authoritative work: break epics into concrete issues on the board, keep an epic open until its children are closed, and never restate the plan as a parallel task list in the repository. Use when splitting an epic, closing an issue that another issue names as its epic, or writing any plan that describes future issues.
---

# Backlog and epic management in dev-org

The board (GitHub Issues/Projects) is the authoritative home of tasks,
backlog, priority, acceptance criteria, dependencies, and decisions. The
system specification's section 4 states this directly: "No parallel task
list in Git." This skill is an operating checklist for the work that
touches that boundary; the specification is authoritative.

## Before splitting an epic

1. Read the repo's [AGENTS.md](../../AGENTS.md), the [work protocol](../../docs/development/work-protocol.md), and the relevant sections of [the specification](../../dev-org-specification.md).
2. Confirm the epic is a "planned epic, not a ready implementation issue" (its body says so) before decomposing it.
3. Break it into concrete issues **on the board**, each with its own acceptance criteria, dependencies, scope, and the A-tests it must pass. Link them in delivery order with the blocked_by chain, and mark each child's body with `Part of epic #N` so the epic's children are findable. (Write `#N` as a placeholder — a concrete number in a tracked file would look like a parallel plan.)
4. Do **not** write the breakdown as a tracked document in the repository. The plan lives on the board; a repo copy duplicates the authoritative source and silently drifts.

## Keeping an epic open

- An epic (`type:epic`) stays open until **every** issue naming it as `Part of epic #N` is closed. Closing the epic while children are open strands them without an open collector.
- A delivery PR for a child closes the child, not the epic. Do not put `Closes #N` for the epic in a PR that delivers only part of it.
- If an epic must be closed early, first close or move all its children; the epic is not closed while any child remains open.

## When writing plans and docs

- Put each fact in its authoritative location and link to it instead of copying it: acceptance criteria live in the issue, decisions live in `decisions/` ADRs, operational guidance lives in skills, and behavior lives in the specification.
- A tracked document may *mention* an issue in prose ("issue #13 delivers handover") or record a decision about it; it must not restate the backlog as a plan (a delivery chain of issue numbers, or `Part of epic #N` markers).

## Enforcement

The repository enforces both sides mechanically, so a mistake turns CI red
instead of passing silently:

- `.github/workflows/checks.yml`'s `epic-close` job refuses a PR whose body
  closes an epic that still has open children.
- `tests/test_no_parallel_task_list.py` fails when a tracked document in
  `docs/` or `decisions/` carries a delivery chain of issue numbers or a
  `Part of epic #N` marker.

Run the repo's checks before opening or updating a PR, and report which
checks actually ran and their result.

If advice in this skill conflicts with the system specification, follow the specification and report the mismatch for correction.
