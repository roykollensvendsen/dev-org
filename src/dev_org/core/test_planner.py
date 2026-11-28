"""Test planner: one selection for local agent and CI, reuse per check.

Implements issue #61 (acceptance tests A06, A07, A13): local agent and CI
compute the same test selection from diff, component dependencies, changed
requirements, and check rules (section 6).

- A06: identical check orders share one CI run, and a priority change
  triggers zero builds (the selection is computed from the diff, not the
  order or priority).
- A07: a shared protocol header change and a targeted mutation of a
  boundary value produce a plan covering both affected sides.
- A13: a handover from agent engine to CI counts the CI cost once, even
  with two consumers of the result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

#: A shared protocol header has two affected sides: the producer and the
#: consumer (A07). A mutation plan must cover both.
BOTH_SIDES = 2


@dataclass(frozen=True)
class Diff:
    """What changed: files, and which component each belongs to."""

    changed_files: tuple[str, ...]
    component_of: dict[str, str] = field(default_factory=dict)  # file -> component

    def components(self) -> frozenset[str]:
        """The components touched by this diff."""
        return frozenset(self.component_of.get(f, "unknown") for f in self.changed_files)


@dataclass(frozen=True)
class TestSelection:
    """The deterministic test set for a diff (section 6)."""

    identity: str  # stable identity: same diff -> same selection
    tests: frozenset[str]
    triggered_by_unknown_impact: bool = False

    def covers(self, test: str) -> bool:
        """Whether a test is in this selection."""
        return test in self.tests


@runtime_checkable
class ComponentMap(Protocol):
    """The component -> test mapping the planner reads (section 4.2, A25)."""

    def tests_for(self, component: str) -> frozenset[str]:
        """The tests that cover a component."""
        ...


class SelectionPlanner:
    """Compute the same selection for local agent and CI (section 6)."""

    def __init__(
        self, *, components: ComponentMap, broad_group: frozenset[str] = frozenset({"test_suite"})
    ) -> None:
        """Bind the planner to the component map and the broad fallback group."""
        self.components = components
        self.broad_group = broad_group

    def select(self, diff: Diff) -> TestSelection:
        """The selection for a diff: the union of its components' tests.

        A file with no known component triggers the broad group, because
        unknown impact must not be assumed narrow (section 6). The identity
        is computed from the diff alone, so a priority change does not
        change the selection (A06).
        """
        touched = diff.components()
        if "unknown" in touched:
            return TestSelection(
                identity=self._identity(diff), tests=self.broad_group, triggered_by_unknown_impact=True
            )
        tests: set[str] = set()
        for component in touched:
            tests |= set(self.components.tests_for(component))
        return TestSelection(identity=self._identity(diff), tests=frozenset(tests))

    def _identity(self, diff: Diff) -> str:
        """A stable identity: same diff bytes -> same identity."""
        return "|".join(sorted(diff.changed_files))


class CheckReuse:
    """Identical check orders share one run; priority changes build nothing (A06)."""

    def __init__(self) -> None:
        """Create an empty reuse table."""
        self._running: dict[str, str] = {}  # identity -> run id

    def order(self, *, identity: str, priority: str) -> str:
        """Order a check; an identical running order returns the same run.

        The run id depends on the identity only, never on the priority, so
        a priority change for an identical check triggers zero builds (A06).
        """
        del priority  # priority must not change the run identity
        if identity in self._running:
            return self._running[identity]  # share the running check
        run_id = f"run-{len(self._running) + 1}"
        self._running[identity] = run_id
        return run_id

    def cost_count(self, identity: str) -> int:
        """How many distinct runs an identity has produced (A13: counted once)."""
        return 1 if identity in self._running else 0


class MutationPlan:
    """A targeted mutation of a boundary value covers both affected sides (A07)."""

    def __init__(self, *, header: str, affected_sides: tuple[str, ...]) -> None:
        """Bind the plan to the shared header and its two affected sides."""
        self.header = header
        self.affected_sides = affected_sides

    def covers_both_sides(self) -> bool:
        """Whether the plan covers at least both sides of the shared header."""
        # A shared protocol header has exactly two affected sides (A07).
        return len(set(self.affected_sides)) >= BOTH_SIDES

    def boundary_case(self, value: str) -> str:
        """The mutated boundary value, used to reveal the agreed change."""
        return f"{self.header}={value}"


__all__ = ["CheckReuse", "ComponentMap", "Diff", "MutationPlan", "SelectionPlanner", "TestSelection"]
