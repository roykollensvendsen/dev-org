# ADR-DEV-001: Small, integrable changes

## Status

Accepted. Decided by the project owner on 2026-11-26.

## Context

dev-org is intended to support autonomous and parallel agent work. The system
specification calls for modular boundaries, independently verifiable work, and
integration without a permanent approval bottleneck. The repository already
records the practical workflow in `AGENTS.md` and
`docs/development/work-protocol.md`.

## Options considered

- Allow each worker to choose its own boundaries and integrate large batches.
  This creates avoidable overlap and makes failures harder to localize.
- Require one central reviewer to approve every implementation detail.
  This makes the reviewer a throughput bottleneck.
- Use small changes with explicit contracts, checks, and temporary ownership
  for shared interfaces. This makes work independently verifiable while
  keeping coordination focused on actual overlap.

## Decision

Use small, end-to-end changes with explicit acceptance criteria and checks.
Assign one temporary owner when a shared contract changes; let independent
work continue against the agreed contract. Integrate frequently and document
concrete blockers rather than creating permanent approval roles.

## Consequences

Changes need clear criteria and may require a short contract agreement before
parallel work begins. The project avoids broad integration batches and does not
make a person the routine approval gate. This process does not replace the
policy and promotion boundaries defined in the system specification.

## Related

- [System specification](../dev-org-specification.md)
- [AGENTS.md](../AGENTS.md)
- [Work protocol](../docs/development/work-protocol.md)
