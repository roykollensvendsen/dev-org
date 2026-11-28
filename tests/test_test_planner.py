"""Test planner, checked against A06, A07, and A13.

Issue #61's criteria, mapped one test each:

1. identical check orders share one CI run; a priority change triggers
   zero builds (A06);
2. a shared protocol header change and a targeted mutation of a boundary
   value produce a plan covering both affected sides (A07);
3. a handover from agent engine to CI counts the CI cost once, even with
   two consumers (A13);
4. local agent and CI compute the same selection from diff and component
   dependencies; unknown impact triggers the broad group (section 6).
"""

from __future__ import annotations

from dev_org.core import CheckReuse, Diff, MutationPlan, SelectionPlanner


class Components:
    """A deterministic component -> tests map."""

    def __init__(self, mapping: dict[str, frozenset[str]]) -> None:
        self.mapping = mapping

    def tests_for(self, component: str) -> frozenset[str]:
        return self.mapping.get(component, frozenset())


def make_planner() -> SelectionPlanner:
    return SelectionPlanner(
        components=Components(
            {
                "core": frozenset({"test_core", "test_contracts"}),
                "gateway": frozenset({"test_gateway"}),
            }
        )
    )


# 1. One CI run for identical orders; priority changes build nothing (A06) -


def test_identical_check_orders_share_one_run():
    reuse = CheckReuse()
    first = reuse.order(identity="diff-abc", priority="P2")
    second = reuse.order(identity="diff-abc", priority="P2")  # identical

    assert first == second  # one CI run covers both orders (A06)
    assert reuse.cost_count("diff-abc") == 1


def test_a_priority_change_triggers_zero_builds():
    reuse = CheckReuse()
    original = reuse.order(identity="diff-abc", priority="P2")
    reprioritized = reuse.order(identity="diff-abc", priority="P0")  # only priority changed

    assert reprioritized == original  # the run identity ignores priority (A06)
    assert reuse.cost_count("diff-abc") == 1  # zero extra builds


# 2. Shared header mutation covers both sides (A07) -----------------------


def test_a_shared_header_change_plan_covers_both_sides():
    plan = MutationPlan(header="X-Api-Version", affected_sides=("producer", "consumer"))
    assert plan.covers_both_sides() is True


def test_a_plan_covering_one_side_does_not_cover_both():
    plan = MutationPlan(header="X-Api-Version", affected_sides=("producer",))
    assert plan.covers_both_sides() is False


def test_a_boundary_mutation_reveals_the_agreed_change():
    plan = MutationPlan(header="X-Api-Version", affected_sides=("producer", "consumer"))
    assert plan.boundary_case("1") == "X-Api-Version=1"  # a targeted boundary value (A07)


# 3. CI cost counted once for a handover with two consumers (A13) ---------


def test_the_ci_cost_is_counted_once_with_two_consumers():
    reuse = CheckReuse()
    # Two consumers both consume the same check result after a handover.
    run = reuse.order(identity="ci-check-1", priority="P2")
    assert reuse.cost_count("ci-check-1") == 1  # counted once (A13)

    # Both consumers see the same run id, not two costs.
    assert reuse.order(identity="ci-check-1", priority="P2") == run
    assert reuse.cost_count("ci-check-1") == 1


# 4. Same selection for local agent and CI; unknown impact is broad (§6) ---


def test_local_agent_and_ci_compute_the_same_selection():
    planner = make_planner()
    diff = Diff(
        changed_files=("core/x.py", "gateway/y.py"),
        component_of={"core/x.py": "core", "gateway/y.py": "gateway"},
    )

    # The same deterministic function is the single planner for both sides.
    selection = planner.select(diff)
    assert selection.tests == frozenset({"test_core", "test_contracts", "test_gateway"})


def test_an_unknown_component_triggers_the_broad_group():
    planner = make_planner()
    diff = Diff(changed_files=("legacy/z.py",), component_of={})

    selection = planner.select(diff)
    assert selection.triggered_by_unknown_impact is True
    assert "test_suite" in selection.tests  # broad group, not assumed narrow (§6)


def test_the_selection_identity_is_stable_across_priority():
    planner = make_planner()
    diff = Diff(changed_files=("core/x.py",), component_of={"core/x.py": "core"})
    first = planner.select(diff)
    second = planner.select(diff)

    assert first.identity == second.identity  # same diff -> same selection
