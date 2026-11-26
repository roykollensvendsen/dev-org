---
name: dev-org-parallel-work
description: Plan and integrate parallel or cross-module development in the dev-org repository. Use when work spans shared contracts, multiple components, or concurrent agents; skip for isolated edits with no shared boundary.
---

# Parallel work in dev-org

Use this skill to keep concurrent repository work independent, testable, and easy to integrate. The system specification is authoritative; this skill is an operating checklist.

## Before splitting work

1. Read the repo's [AGENTS.md](../../AGENTS.md), [work protocol](../../docs/development/work-protocol.md), and the relevant sections of [the specification](../../dev-org-spesifikasjon.md).
2. Confirm the backlog item has a concrete result, acceptance criteria, known dependencies, affected components/contracts, and a verification path.
3. Map file and contract overlap. Keep tightly coupled changes together. For a shared contract, name one temporary owner and agree on the interface and compatibility before parallel implementation.
4. Assign only work that can start now. Express real blockers as dependencies; do not create artificial ordering between independent tasks.

## While implementing

- Give each concurrent change its own branch and writable worktree.
- Work against established ports and contract tests or test doubles. Do not invent a competing interface to avoid waiting for a necessary contract decision.
- Keep changes small and integrate when their acceptance criteria pass. Stop duplicate or obsolete jobs that consume shared CI or test capacity.
- If overlap or an unknown dependency appears, pause only the conflicting part, record the concrete blocker, and agree ownership or sequencing. Continue independent work.
- Treat scarce workers, CI capacity, test environments, physical benches, and external quotas as scheduled resources.

## Integrate and report

Verify the affected component and contract, then verify the actual combined change with the repository's documented checks. Do not claim a check ran unless it did. Report changed behavior, shared contracts, verification evidence, remaining blockers, and integration risks. Use observed queue time, conflict/rework rate, integration failures, and CI wait to identify the next bottleneck; do not use agent count as a proxy for throughput.

If advice in this skill conflicts with the system specification, follow the specification and report the mismatch for correction.
