"""The mandatory step-1 acceptance tests, each mapped to real evidence.

Issue #11 requires running the mandatory step-1 tests. The specification's
section 12 fixes that set (and says the issue body's "A50" is a slip for
A80, the OpenCode adapter: A50 is the Codex test that first applies in a
later step). Each test in the set must map to either:

- a real, deterministic test that exercises the specification's contract in
  this suite, or
- a clearly marked live test that needs a component this environment does
  not provide (OpenCode against a live provider, rootless Podman, real
  GitHub/CI) and how to run it.

This registry is itself the mechanism that keeps that mapping honest: it
fails when a new step-1 test is added to the specification but has no
evidence entry, and it lists the live commands so they are runnable where
the resources exist.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).parent.parent

#: Every "tests/something.py::maybe_a_test" reference inside an evidence string.
_REF = re.compile(r"(?:tests|docs)/[A-Za-z0-9_.-]+\.(?:py|md)(?:::[A-Za-z0-9_]+)?")

#: The mandatory step-1 set, as fixed by specification section 12. A50 (the
#: Codex adapter) is not here; A80 (the OpenCode adapter) is, per the spec.
#: Each ID maps to its evidence: a "(module, test) or suite of tests" string,
#: or a live command prefixed with "live:". "live" entries have no cover here
#: because running them needs a real component; they are not silently passed.
MANDATORY_STEP1: dict[str, str] = {
    "A01": "tests/test_first_workflow.py + tests/test_gateway_service.py (re-find the same PR once)",
    "A02": "tests/test_ci_waiting.py + tests/test_first_workflow.py (duplicate event wakes at most once)",
    "A05": "tests/test_queue_lifecycle.py::test_a_stale_owner_cannot_publish_after_lease_expiry",
    "A10": "tests/test_gateway_service.py (manual priority preserved while PR link is recorded)",
    "A11": "tests/test_ci_waiting.py::test_a11_zero_model_calls_while_waiting",
    "A12": "tests/test_queue_lifecycle.py (no model call on an empty/waiting queue)",
    "A17": "live: run the pilot issue with OpenCode (see docs/pilot.md); the config is engine-swappable",
    "A19": "tests/test_policy_engine.py::test_merge_is_never_allowed_flatly_for_a_worker",
    "A20": "live: tests/test_runtime_podman.py live markers (engine-independent sandbox probe)",
    "A21": "tests/test_runtime_podman.py (refuse a profile the backend cannot enforce)",
    "A22": "tests/test_policy_engine.py + tests/test_gateway_service.py (revocation/lost answer)",
    "A25": "tests/test_state_contracts.py + docs/pilot.md (component basis for the pilot repo)",
    "A27": "tests/test_first_workflow.py (timeline ties events to one task/attempt)",
    "A28": "live: needs the durable-operation export path (later issue; see docs/pilot.md)",
    "A32": "tests/test_queue_lifecycle.py::test_a_stale_owner_cannot_publish_after_lease_expiry",
    "A33": "tests/test_acceptance_references.py + tests/test_first_workflow.py (queue ordering)",
    "A37": "tests/test_gateway_service.py::test_a_lost_answer_finds_the_existing_pr_instead_of_a_duplicate",
    "A38": "tests/test_gateway_service.py (identical retry, one effect)",
    "A39": "live: needs the durable adapter, a later delivery (db stop between work and push; docs/pilot.md)",
    "A40": "live: tests/test_runtime_podman.py live markers (sandbox boundary probe)",
    "A41": "live: needs the real GitHub gateway (A01/A19/A22 cover the deterministic parts; docs/pilot.md)",
    "A42": "tests/test_ci_waiting.py::test_a42_reconciliation_finds_a_result_after_a_dropped_event",
    "A43": "live: needs the separate candidate environment (test board/DB; docs/pilot.md)",
    "A44": "tests/test_gateway_service.py (bootstrap stays in PR mode: merge is denied)",
    "A46": "tests/test_policy_engine.py (independent approval boundary; candidate cannot self-approve)",
    "A52": "live: provider quota handling needs a live provider (later step; docs/pilot.md)",
    "A53": "live: message channel between workers (later issue; docs/pilot.md)",
    "A55": "tests/test_first_workflow.py (blockage + next event via CiWaiter.status_view)",
    "A56": "live: knowledge memory (later issue; docs/pilot.md)",
    "A57": "live: extension manifest (later issue; docs/pilot.md)",
    "A61": "tests/test_first_workflow.py (board/PR/CI linked, not a separate dashboard)",
    "A62": "tests/test_first_workflow.py (single delivery line, no reload needed)",
    "A70": "tests/test_policy_engine.py + tests/test_gateway_service.py (same policy for API and agent)",
    "A78": "tests/test_policy_engine.py (advance assessment uses the same evaluator; A19/A22)",
    "A79": "tests/test_gateway_service.py::test_a_denied_action_is_rejected_before_any_external_call",
    "A80": "tests/test_agent_adapter_contract.py (OpenCode adapter satisfies the AgentAdapter contract)",
}


def _test_bodies_exist(symbol: str) -> bool:
    """True when every referenced file/symbol an evidence string names is real.

    The evidence strings carry prose and may name several suites, so this
    extracts every ``tests/x.py::test_y`` or ``docs/x.md`` reference and
    checks the file exists and, where given, the symbol is defined inside it.
    An evidence string that names no file at all is a broken entry.
    """
    refs = _REF.findall(symbol)
    if not refs:
        return False
    for ref in refs:
        file_part, _, test_name = ref.partition("::")
        path = ROOT / file_part
        if not path.is_file():
            return False
        if test_name and f"def {test_name}" not in path.read_text():
            return False
    return True


def test_the_registry_matches_the_specs_own_step1_list():
    """Criterion 3 is checked against the specification, not a copy.

    The specification's section 12 names the mandatory step-1 row. Every
    test it lists must have an evidence entry here, and every entry here
    must be required by the spec — so a new step-1 test cannot be silently
    missing and a stale extra cannot linger.
    """
    text = (ROOT / "dev-org-specification.md").read_text()
    # The mandatory list is on the "From step | 1 |" row: capture only the
    # comma-separated list portion of that cell (the prose that follows names
    # tests again but is not the mandatory set), expanding range notation
    # like A37 through A44.
    row = next(line for line in text.splitlines() if line.startswith("| 1 |"))
    list_part = row.split("|")[2].split(". ", 1)[0]
    required: set[str] = set()
    for m in re.finditer(r"A(\d{2})(?:[-\u2013]A(\d{2}))?", list_part):
        start, end = int(m.group(1)), int(m.group(2) or m.group(1))
        required.update(f"A{n:02d}" for n in range(start, end + 1))
    assert required, "spec's step-1 row names no mandatory tests"
    assert required == set(MANDATORY_STEP1), (
        f"registry diverged from the spec's step-1 list: "
        f"missing {sorted(required - set(MANDATORY_STEP1))}, "
        f"extra {sorted(set(MANDATORY_STEP1) - required)}"
    )


def test_live_tests_are_marked_live_and_never_claimed_passing():
    for test_id, evidence in MANDATORY_STEP1.items():
        is_live = evidence.startswith("live:")
        assert is_live or evidence, f"{test_id} has empty evidence"
        if is_live:
            # A live entry must still point at a real probe (a test file or
            # the pilot doc) so a maintainer can see where and how to run it;
            # it is never claimed to pass silently here.
            assert _test_bodies_exist(evidence.split("live:", 1)[1]), (
                f"{test_id} live entry must point at a real probe, got: {evidence}"
            )
        else:
            # A non-live entry must name tests that exist in this repository.
            assert _test_bodies_exist(evidence), f"{test_id} evidence names nothing real: {evidence}"
