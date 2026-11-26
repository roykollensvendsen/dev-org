# ADR-DEV-004: First pilot basis and verification definition

## Status

Accepted. Decided by the project owner on 2026-11-26.

## Context

Issue #3 closes the technical and operational basis for the first
delivery: which language and tooling, which transactional store, which
agent engine and Linux backend, and what a verified delivery means. The
specification's MVP decisions (section 10) already settle most of these
choices; this record gathers them into one place, references the
authoritative section for each, records what the pilot machine still
needs, and defines the pilot bug and the verified-PR criterion that the
acceptance tests need.

## Technical basis (referenced, not copied)

The binding choices are in the specification and are not restated here:

- **Language and API:** Python 3.14.x, FastAPI, Pydantic 2.x, OpenAPI
  3.1 — [specification 10.1](../dev-org-specification.md).
- **Transactional store:** PostgreSQL 16.x, SQLAlchemy 2.x, Alembic —
  [specification 10.1](../dev-org-specification.md). PostgreSQL is
  authoritative for the internal queue, reservations, approvals,
  operations journal, events, and state.
- **Board and CI:** GitHub Projects v2/Issues and GitHub Actions —
  [specification 10.2](../dev-org-specification.md).
- **First agent engine:** OpenCode, authenticated through its configured
  provider APIs (chutes, openrouter, anthropic) — [ADR-DEV-003](ADR-DEV-003-use-opencode-first-engine.md)
  and [specification 10.2](../dev-org-specification.md).
- **Linux backend:** rootless Podman, one container per attempt —
  [specification 10.2](../dev-org-specification.md).

## Resource profile

The default per-attempt profile is set by the specification and applies
as-is: at most 2 CPU cores, 4 GiB memory, 256 processes/threads, 20 GiB
writable workspace, and 90 minutes wall clock time
([specification 10.2](../dev-org-specification.md)). The pilot uses the
default; no higher limits are requested in the first delivery.

## What the pilot machine still needs

Two runtime dependencies for step 1 are not present on this machine and
must be installed before the runtime and queue issues can be qualified:

- **Podman** (rootless) is not installed; it is the execution backend for
  the attempt container ([issue #7](https://github.com/roykollensvendsen/dev-org/issues/7)).
- **PostgreSQL** is installed (psql 18.6) but the service is not running
  on its socket; it must be started before the durable queue can be
  exercised ([issue #5](https://github.com/roykollensvendsen/dev-org/issues/5)).

## The pilot bug

A harmless, reproducible pilot bug in a small, contained function, so the
first end-to-end run can show a check failing before the fix and passing
after it. It must not touch real data, security, or external systems.

The chosen pilot bug: **a string-normalization helper in the core that
fails to collapse multiple consecutive spaces**, so a title like
"OpenCode  first  run" is kept with doubled spaces instead of being
normalized to "OpenCode first run". It lives in a pure function with a
unit test, is invisible to anything outside its caller, and is fixed by
changing one line. The first pilot task will reproduce it, show the test
red, fix it, and show the test green.

Expected behavior: the helper returns the input trimmed and with runs of
whitespace collapsed to a single space, preserving the content.

## What a verified PR means in the pilot

A pull request is verified when all of these hold:

1. The mandatory checks pass: `commits` (conventional commits and
   imperative subjects) and `checks (3.14)` (lint, format, types, and the
   full test suite) — the branch-protection status checks on `main`.
2. The acceptance criteria of the issue it closes are met, shown by the
   test evidence in the PR body.
3. The change was seen red before it was green: the test fails on the
   pre-fix state and passes after, and the PR says which run showed that.
4. A human reviewer approved the PR; no agent approves its own change
   ([specification 10.3](../dev-org-specification.md)).

## Consequences

- The pilot has a concrete, harmless bug to run end to end, so step 1
  has a real target instead of a generic "first workflow".
- Podman installation and PostgreSQL startup are recorded as concrete
  prerequisites on the issues that need them, so work is not silently
  blocked.
- The verified-PR definition gives the gateway and CI work a measurable
  target in [issue #10](https://github.com/roykollensvendsen/dev-org/issues/10)
  and the pilot [issue #11](https://github.com/roykollensvendsen/dev-org/issues/11).

## Related

- [System specification, section 10](../dev-org-specification.md)
- [System specification, section 11](../dev-org-specification.md)
- [ADR-DEV-003: Use OpenCode as the first agent engine](ADR-DEV-003-use-opencode-first-engine.md)
