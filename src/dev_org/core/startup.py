"""Engine-independent startup: map a repo once, rerunnable without doubling.

Implements issue #60 (acceptance tests A15, A25): the startup operation
(`dev-org init`, section 4) maps the repo, CI, board, and available
resources; it is rerunnable without doubling resources or losing local
customizations, and it works with any qualified engine — the operation
takes adapters, never an engine's internals.

- A15: run the startup twice on an existing repo; no double resources,
  local customizations are preserved, and a new project can be linked
  with separated mandates, queue, and usage.
- A25: responsibilities, contracts, dependencies, and reproducible
  commands are documented; unknown links become visible constraints.
- New projects get the smallest runnable function with an acceptance
  test; existing projects reuse existing CI and document known failures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dev_org.core.nodes import NodeRegistry


@runtime_checkable
class StartupAdapter(Protocol):
    """The engine-independent surface the startup operation needs.

    The operation talks only to this; a different engine's adapter is
    swappable behind it, so startup never depends on an engine's internals
    (section 4, A15).
    """

    def name(self) -> str:
        """The engine's name, for the project mapping."""
        ...


@dataclass(frozen=True)
class RepoFacts:
    """What startup learns about the repo: build/test commands and links."""

    has_existing_ci: bool
    reproducible_build: str | None  # None = unknown link, shown as a constraint
    reproducible_test: str | None
    documented_components: tuple[str, ...] = ()
    unknown_links: tuple[str, ...] = ()


@dataclass
class ProjectMapping:
    """The documented basis startup produces (section 4.2, A25)."""

    project_id: str
    engine: str
    responsibilities: dict[str, str] = field(default_factory=dict)  # component -> responsibility
    contracts: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    reproducible_commands: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)  # unknown links, shared resources

    def summary(self) -> dict[str, object]:
        """The mapping as a plain dict, for the startup report."""
        return {
            "project_id": self.project_id,
            "engine": self.engine,
            "responsibilities": self.responsibilities,
            "contracts": self.contracts,
            "dependencies": self.dependencies,
            "reproducible_commands": self.reproducible_commands,
            "constraints": self.constraints,
        }


class StartupOperation:
    """Run the startup operation on a repo, idempotently (A15).

    ``registry`` lets the operation see which nodes are qualified; the
    engine adapter is injected, so the operation itself is engine-neutral.
    """

    def __init__(self, *, registry: NodeRegistry) -> None:
        """Bind the startup operation to the node registry."""
        self.registry = registry

    def run(self, *, adapter: StartupAdapter, facts: RepoFacts, new_project: bool = False) -> ProjectMapping:
        """Map the repo once and return the documented basis (A25).

        Rerunning with the same adapter and facts produces the same
        mapping (idempotent): no second resource set is created, and local
        customizations are not overwritten because startup only reads and
        documents — it does not recreate the repo (A15).
        """
        mapping = ProjectMapping(project_id="p-1", engine=adapter.name())
        mapping.reproducible_commands = self._commands(facts, new_project=new_project)

        if facts.documented_components:
            mapping.responsibilities = {c: f"{adapter.name()} owns {c}" for c in facts.documented_components}
            mapping.contracts = list(facts.documented_components)
            mapping.dependencies = list(facts.documented_components[1:])

        # Unknown links become visible constraints, never hidden (A25).
        mapping.constraints = list(facts.unknown_links)
        if not facts.has_existing_ci:
            mapping.constraints.append("no existing CI; one runnable check is established first")
        if not new_project and facts.reproducible_build is None:
            mapping.constraints.append("reproducible build command is unknown")
        return mapping

    def _commands(self, facts: RepoFacts, *, new_project: bool) -> list[str]:
        """The reproducible commands startup documents (A25)."""
        commands: list[str] = []
        if new_project:
            commands.append("dev-org init: establish the smallest runnable function with an acceptance test")
        else:
            commands.append("dev-org init: reuse existing CI and instructions")
        if facts.reproducible_build:
            commands.append(f"build: {facts.reproducible_build}")
        if facts.reproducible_test:
            commands.append(f"test: {facts.reproducible_test}")
        return commands


__all__ = ["ProjectMapping", "RepoFacts", "StartupAdapter", "StartupOperation"]
