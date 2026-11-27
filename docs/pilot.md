# The first pilot workflow

Issue #11 demonstrates the first delivery loop end to end: a bug report on
the board becomes a verified pull request, delivered once, surviving a
restart. This page records what the pilot fixes, which measured time and
cost limits it enforces, which of the mandatory step-1 acceptance tests it
runs here, and the known limitations — the parts that need a live component
this simulated delivery does not provide.

## The pilot bug

The queue served ready tasks in insertion order regardless of priority, so
a lower-priority task created earlier could be handed to a worker before a
higher-priority one that was already ready. The specification's section 1
says dev-org must first do the client's highest-priority clarified work, and
acceptance test A03 requires priority to carry all the way to the necessary
resource.

The agreed check is `tests/test_queue_priority.py`:

- it was red before the fix (`next_ready` returned the P2 task);
- it is green after the fix, where `Store.ready_tasks` orders the ready
  queue by priority (P0 first) and keeps it stable within equal priority.

## What the delivery loop shows

`tests/test_first_workflow.py` runs the whole line with a simulated clock,
worker, board, Git/PR, and CI against the deterministic in-memory store:

- the high-priority bug report is picked first (this fix);
- the gateway opens exactly one PR and re-finds it after a restart or a lost
  answer (A01, A37, A38);
- the worker holds the session on CI, and reconciliation wakes at most one
  continuation (A02, A11);
- the delivery completes and the result is checked independently (one PR, a
  linked board status).

## Mandatory step-1 acceptance tests

The full mapping lives in `tests/test_mandatory_step1_registry.py`. Each of
the step-1 tests from specification section 12 maps to either a test that
runs in this suite or a clearly marked live test and how to run it. The
registry fails if a non-live entry names nothing real, so a renamed or
deleted test cannot leave a stale claim.

## Measured time and cost limits

The pilot is a simulated delivery; there is no live model usage, so there
is no real model cost. The limits the architecture enforces are:

| Limit | Value | Where enforced |
|---|---|---|
| Active attempts per repo | At most 1 | lifecycle reservation (A05) |
| Attempts per issue | 3, then a concrete blockage | reserved for the live runner |
| Active-model minutes per time | 60 per issue | reserved for the live runner |
| CI wait | worker session ended while waiting (A11) | `CiWaiter` |
| Provider cost cap | unknown (no enforceable basis) | shown as unknown in the timeline |

Money usage is shown as unknown because the simulated provider exposes no
enforceable measurement basis; the time and attempt caps are what the pilot
actually enforces. This matches the specification's section 11: when the
provider does not expose an enforceable cost basis, runtime and attempt
count still have hard limits while money usage is shown as unknown.

## Known limitations

The pilot is deterministic and runs in-process, which is exactly what the
specification's section 12 asks for the queue, policy, and state machine.
The parts that need a real component are documented here and in the step-1
registry as live tests:

- **OpenCode adapter end to end (A80, A17).** The adapter satisfies the
  `AgentAdapter` contract (`tests/test_agent_adapter_contract.py`), but a
  real run needs the pinned OpenCode CLI talking to a live provider. Run:
  `uv run python -m pytest tests/test_agent_adapter_contract.py`, then a
  live agent run against the pilot repo with the OpenCode adapter selected.
- **Sandbox isolation (A20, A40).** Rootless Podman probes are written as
  live markers in `tests/test_runtime_podman.py` and run where `podman` is
  installed (`uv run pytest -m live`); they are skipped in CI because CI has
  no Podman.
- **Real GitHub board/Git/CI (A41).** The deterministic doubles prove the
  ordering; the real gateway needs the GitHub App install and CI, and a
  live run opens a real PR waiting on real checks.
- **Later-issue subsystems.** Durable-operation export (A28), provider
  quota handling (A52), the worker message channel (A53), knowledge memory
  (A56), and the extension manifest (A57) each need their own delivery and
  are called out as live in the registry rather than being quietly passed.

These are not false passes: the registry refuses to claim a live test
passes in an environment that cannot run it.
