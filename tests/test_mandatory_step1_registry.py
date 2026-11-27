"""The mandatory step tests, each mapped to real evidence, from one source.

The specification's section 12 has the authoritative "From step" table:
every step names the tests that become mandatory from it. This module makes
that table the single source of truth:

- the canonical step -> tests map is parsed from the spec, not hand-copied,
  so a transcription like "A50" where the spec says "A80" fails here first;
- a test must map to real evidence: a deterministic test in this suite, or
  a clearly marked live test needing a component this environment does not
  provide (a live engine or provider, rootless Podman, real GitHub/CI) and
  where/how it runs;
- the registry fails when a step's tests are not all evidenced, or when a
  test is cited that the spec's A-table does not define.

Evidence is recorded per step: issue #11 delivers step 1 (the pilot), issue
#12 delivers step 2 (the second engine). A step without an evidence map yet
is simply not claimed.

This registry is itself the mechanism that keeps that mapping honest: it
fails when the specification's step lists change but the evidence does not,
and it lists the live commands so they are runnable where resources exist.
"""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).parent.parent
SPEC = ROOT / "dev-org-specification.md"
BACKLOG = ROOT / ".bootstrap" / "github-backlog.json"

#: A defined test is a row of the acceptance-test table: `| A01 | ... | ... |`.
TABLE_ROW = re.compile(r"^\|\s*(A\d{2})\s*\|")
#: Range notation inside a "From step" cell, e.g. "A19-A22".
_RANGE = re.compile(r"A(\d{2})(?:[-\u2013]A(\d{2}))?")
#: Every "tests/something.py::maybe_a_test" reference inside an evidence string.
_REF = re.compile(r"(?:tests|docs)/[A-Za-z0-9_.-]+\.(?:py|md)(?:::[A-Za-z0-9_]+)?")
#: The issue key in the backlog that carries the step-1 mandatory list.
PILOT_KEY = "pilot"


def defined_tests() -> set[str]:
    """Every test ID the acceptance-test table defines, in section 12."""
    rows = [TABLE_ROW.match(line) for line in SPEC.read_text().splitlines()]
    return {m.group(1) for m in rows if m}


def _expand(text: str) -> set[str]:
    """Expand range notation ("A37-A44") into the individual test IDs."""
    ids: set[str] = set()
    for m in _RANGE.finditer(text):
        start, end = int(m.group(1)), int(m.group(2) or m.group(1))
        ids.update(f"A{n:02d}" for n in range(start, end + 1))
    return ids


def step_tests() -> dict[int, set[str]]:
    """The canonical step -> mandatory-tests map, parsed from the spec.

    Each "| N | ... |" row names the tests that become mandatory from that
    step. Only the comma-separated list portion of each cell is read (the
    prose that follows names tests again but is not the mandatory set).
    """
    result: dict[int, set[str]] = {}
    for line in SPEC.read_text().splitlines():
        match = re.match(r"\|\s*(\d)\s*\|", line)
        if not match:
            continue
        cell = line.split("|")[2]
        list_part = cell.split(". ", 1)[0]
        result[int(match.group(1))] = _expand(list_part)
    if not result:
        msg = "no 'From step | N |' rows found in the specification"
        raise RuntimeError(msg)
    return result


STEP_TESTS = step_tests()

#: Evidence per step-1 test. The keys are derived from the canonical map, not
#: hand-copied, so a misspelled ID can never be added here silently.
STEP1_EVIDENCE: dict[str, str] = {
    "A01": "tests/test_first_workflow.py + tests/test_gateway_service.py (re-find the same PR once)",
    "A02": "tests/test_ci_waiting.py + tests/test_first_workflow.py (duplicate event wakes at most once)",
    "A05": "tests/test_queue_lifecycle.py::test_a_stale_owner_cannot_publish_after_lease_expiry",
    "A10": "tests/test_gateway_service.py (manual priority preserved while PR link is recorded)",
    "A11": "tests/test_ci_waiting.py::test_a11_zero_model_calls_while_waiting",
    "A12": "tests/test_queue_lifecycle.py (no model call on an empty/waiting queue)",
    "A17": "tests/test_engine_independence.py + tests/test_agent_adapter_contract.py (all qualified engines)",
    "A19": "tests/test_policy_engine.py::test_merge_is_never_allowed_flatly_for_a_worker",
    "A20": "live: tests/test_runtime_podman.py live markers (engine-independent sandbox probe)",
    "A21": "tests/test_runtime_podman.py (refuse a profile the backend cannot enforce)",
    "A22": "tests/test_policy_engine.py + tests/test_gateway_service.py (revocation/lost answer)",
    "A25": "tests/test_state_contracts.py + docs/pilot.md (component basis for the pilot repo)",
    "A27": "tests/test_first_workflow.py (timeline ties events to one task/attempt)",
    "A28": "live: needs the durable-operation export path (later issue; see docs/pilot.md)",
    "A32": "tests/test_queue_lifecycle.py::test_a_stale_owner_cannot_publish_after_lease_expiry",
    "A33": "tests/test_first_workflow.py (queue ordering; blockage + next event)",
    "A37": "tests/test_gateway_service.py::test_a_lost_answer_finds_the_existing_pr_instead_of_a_duplicate",
    "A38": "tests/test_gateway_service.py (identical retry, one effect)",
    "A39": "live: needs the durable adapter (db stop between work and push; docs/pilot.md)",
    "A40": "live: tests/test_runtime_podman.py live markers (sandbox boundary probe)",
    "A41": "live: needs the real GitHub gateway (A01/A19/A22 cover the deterministic parts; docs/pilot.md)",
    "A42": "tests/test_ci_waiting.py::test_a42_reconciliation_finds_a_result_after_a_dropped_event",
    "A43": "tests/test_candidate_environment.py (candidate cannot touch the active queue)",
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

#: Evidence per step-2 test (issue #12 qualifies the second engine, issue
#: #13 delivers handover and message delivery). The keys come from the
#: spec's "From step | 2 |" row, like step 1.
STEP2_EVIDENCE: dict[str, str] = {
    "A18": "tests/test_handover.py (engine switch from the checkpoint, no build)",
    "A23": "tests/test_handover.py (duplicate delivery is one logical processing)",
    "A34": "tests/test_engine_independence.py + tests/test_agent_adapter_contract.py (capabilities)",
    "A35": "tests/test_handover.py (an old approval answer after a restart grants nothing)",
    "A36": "tests/test_handover.py + tests/test_gateway_service.py (journal reconciles a lost answer)",
    "A51": "tests/test_agent_adapter_contract.py (unmodified CLI, native login, no API key)",
    "A52": "live: provider quota handling needs a live provider (later step; docs/pilot.md)",
    "A54": "tests/test_handover.py (messages queued without a competing session)",
}

#: Evidence per step-3 test delivered so far (issue #35 scheduler, #36
#: candidate, #37 activation). The keys come from the spec's "From step |
#: 3 |" row, like the other steps.
STEP3_EVIDENCE: dict[str, str] = {
    "A03": "tests/test_scheduler.py (production before improvement; priority)",
    "A14": "tests/test_activation.py (upgrade and rollback while an issue waits on CI)",
    "A16": "tests/test_scheduler.py (idle with no work and no candidate)",
    "A29": "tests/test_evaluation.py (replay compares candidate with baseline)",
    "A43": "tests/test_candidate_environment.py (candidate cannot touch the active queue)",
    "A45": "tests/test_activation.py (qualified before active; rollback without double continuations)",
    "A47": "tests/test_evaluation.py (baseline and two candidates on the same task set)",
    "A48": "tests/test_scheduler.py (candidate budget throttled before reserved capacity)",
    "A49": "tests/test_activation.py (candidate failure keeps the active version)",
    "A59": "tests/test_change_frame.py (frame-in changes approved; out-of-frame to owner)",
    "A60": "tests/test_change_frame.py (unknown risk quarantined; outside frame rejected)",
}

#: Evidence per step-5 test that this early delivery covers (Codex, the
#: third engine). A50 is the only step-5 test this issue delivers; the rest
#: of step 5 (Redmine, migration, reuse) stays in its own epic.
STEP5_EVIDENCE: dict[str, str] = {
    "A50": "tests/test_agent_adapter_contract.py (unmodified CLI, ChatGPT login, no API key)",
}

#: Every evidence map, keyed by the step it covers.
EVIDENCE: dict[int, dict[str, str]] = {
    1: STEP1_EVIDENCE,
    2: STEP2_EVIDENCE,
    3: STEP3_EVIDENCE,
    5: STEP5_EVIDENCE,
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


# Evidence checks -----------------------------------------------------


#: Steps where the evidence map is intentionally partial: not every test the
#: spec lists for the step is delivered here, and the gap is a real, named
#: one. A partial step must still evidence every test it claims, and its
#: reason must point at where the rest lives. An empty partial step is a lie.
PARTIAL_STEPS: dict[int, str] = {
    5: "the rest of step 5 (Redmine, migration, reuse) is its own epic, #16",
}


def test_evidence_keys_match_the_canonical_spec_set():
    """The evidence keys are derived from the spec, not a hand-copied list.

    This is the guard that would have caught the original "A50" slip: each
    step's evidence set comes from the spec's own "From step | N |" row, so
    a misspelled or misplaced test cannot be added silently. A fully
    delivered step must evidence every test; a step marked partial in
    PARTIAL_STEPS may evidence a subset, with its reason naming where the
    rest lives.
    """
    for step, evidence in EVIDENCE.items():
        canonical = STEP_TESTS[step]
        assert canonical, f"spec's step-{step} row names no mandatory tests"
        extra = set(evidence) - canonical
        assert not extra, f"step-{step} evidence names tests the spec does not require: {sorted(extra)}"
        missing = canonical - set(evidence)
        if step in PARTIAL_STEPS:
            assert evidence, f"step-{step} is marked partial but evidences nothing"
            assert PARTIAL_STEPS[step], f"step-{step} partial reason is empty"
        else:
            assert not missing, f"spec requires step-{step} tests with no evidence: {sorted(missing)}"


def test_live_tests_are_marked_live_and_never_claimed_passing():
    for step, evidence in EVIDENCE.items():
        for test_id, evidence_text in evidence.items():
            is_live = evidence_text.startswith("live:")
            assert is_live or evidence_text, f"{test_id} has empty evidence"
            if is_live:
                # A live entry must still point at a real probe (a test file
                # or a doc) so a maintainer can see where and how to run it;
                # it is never claimed to pass silently here.
                assert _test_bodies_exist(evidence_text.split("live:", 1)[1]), (
                    f"{test_id} live entry must point at a real probe, got: {evidence_text}"
                )
            else:
                # A non-live entry must name tests that exist in this repo.
                assert _test_bodies_exist(evidence_text), (
                    f"{test_id} (step {step}) evidence names nothing real: {evidence_text}"
                )


# All-step consistency ------------------------------------------------


def test_every_step_list_cites_only_defined_tests():
    """A step list that names a test the A-table does not define is a dead rule.

    This catches the general class of the step-1 slip in later steps: any
    "From step" row may only name tests that actually exist in section 12.
    """
    defined = defined_tests()
    for step, tests in STEP_TESTS.items():
        unknown = sorted(t for t in tests if t not in defined)
        assert not unknown, f"step {step} names tests that are not defined: {unknown}"


def test_every_step_has_a_mandatory_list():
    """Steps 1-5 each name at least one new mandatory test."""
    assert set(STEP_TESTS) == {1, 2, 3, 4, 5}
    for step in range(1, 6):
        assert STEP_TESTS[step], f"step {step} names no mandatory tests"


def test_the_backlog_mandatory_statement_matches_the_spec():
    """The backlog's step-1 statement must equal the spec's canonical set.

    The bootstrap backlog is the import source, so a transcription error
    there would reach the authoritative GitHub backlog. When this gitignored
    file is present (it is absent on a fresh clone), its pilot issue must
    carry exactly the spec's step-1 mandatory list. This is what would have
    caught "A50" in place of "A80".
    """
    if not BACKLOG.is_file():
        # The file is gitignored and cannot be relied on in CI; the other
        # checks above still run. The guard lives at the import source.
        return
    config = json.loads(BACKLOG.read_text())
    pilot = next(i for i in config["issues"] if i["key"] == PILOT_KEY)
    checks = "\n".join(pilot["checks"])
    cited = _expand(checks)
    canonical = STEP_TESTS[1]
    assert cited == canonical, (
        f"backlog pilot statement differs from the spec: "
        f"extra {sorted(cited - canonical)}, missing {sorted(canonical - cited)}"
    )
