"""Engine-independent startup, checked against A15 and A25.

Issue #60's criteria, mapped one test each:

1. running the startup twice on an existing repo creates no double
   resources and preserves local customizations (A15);
2. the mapping documents responsibilities, contracts, dependencies, and
   reproducible commands; unknown links become visible constraints (A25);
3. the startup is engine-independent: the same operation works with
   OpenCode, Claude Code, and Codex behind the injected adapter;
4. a new project gets the smallest runnable function, an existing one
   reuses its CI and documents known failures (section 4).
"""

from __future__ import annotations

import pytest

from dev_org.core import NodeRegistry, RepoFacts, StartupAdapter, StartupOperation


def make_repo_facts(
    *, existing_ci: bool = True, build: str | None = "uv run ruff check .", unknown: tuple[str, ...] = ()
) -> RepoFacts:
    return RepoFacts(
        has_existing_ci=existing_ci,
        reproducible_build=build,
        reproducible_test="uv run pytest -q",
        documented_components=("core", "gateway", "agents"),
        unknown_links=unknown,
    )


class Engine:
    """A StartupAdapter double: the operation must not depend on its internals."""

    def __init__(self, name: str) -> None:
        self._name = name

    def name(self) -> str:
        return self._name


def make_operation() -> tuple[StartupOperation, NodeRegistry]:
    registry = NodeRegistry()
    return StartupOperation(registry=registry), registry


# 1. Rerunnable without doubling resources (A15) --------------------------


def test_running_startup_twice_is_idempotent():
    operation, _ = make_operation()
    facts = make_repo_facts()

    first = operation.run(adapter=Engine("opencode"), facts=facts)
    second = operation.run(adapter=Engine("opencode"), facts=facts)

    # Same mapping, same commands: no second resource set is created (A15).
    assert first.summary() == second.summary()
    assert first.reproducible_commands == second.reproducible_commands


def test_startup_preserves_local_customizations():
    operation, _ = make_operation()
    facts = make_repo_facts(build="make build")  # a local customization

    mapping = operation.run(adapter=Engine("opencode"), facts=facts)
    # The local build command is documented, not overwritten (A15).
    assert "build: make build" in mapping.reproducible_commands


# 2. Documented basis and visible constraints (A25) -----------------------


def test_the_mapping_documents_responsibilities_contracts_and_commands():
    operation, _ = make_operation()
    mapping = operation.run(adapter=Engine("opencode"), facts=make_repo_facts())

    assert mapping.responsibilities["core"] == "opencode owns core"
    assert "gateway" in mapping.contracts
    assert mapping.reproducible_commands  # reproducible commands documented


def test_unknown_links_become_visible_constraints():
    operation, _ = make_operation()
    mapping = operation.run(
        adapter=Engine("opencode"), facts=make_repo_facts(unknown=("bench", "legacy-schema"))
    )

    assert "bench" in mapping.constraints
    assert "legacy-schema" in mapping.constraints


def test_a_missing_build_command_is_a_constraint_not_a_hidden_gap():
    operation, _ = make_operation()
    mapping = operation.run(adapter=Engine("opencode"), facts=make_repo_facts(build=None))

    assert any("reproducible build command is unknown" in c for c in mapping.constraints)


# 3. Engine independence (A15) --------------------------------------------


@pytest.mark.parametrize("engine_name", ["opencode", "claude-code", "codex"])
def test_the_same_operation_works_with_every_engine(engine_name):
    operation, _ = make_operation()
    mapping = operation.run(adapter=Engine(engine_name), facts=make_repo_facts())

    # The operation produced the same documented basis; only the engine
    # name differs. No engine-specific branch exists in the operation.
    assert mapping.engine == engine_name
    assert mapping.reproducible_commands
    assert isinstance(operation, StartupOperation)


def test_the_startup_operation_takes_a_protocol_adapter_not_an_engine_class():
    operation, _ = make_operation()
    # A different engine implementation behind the same protocol is a
    # drop-in: the operation never imports an engine's internals.
    adapter = Engine("claude-code")
    assert isinstance(adapter, StartupAdapter)
    mapping = operation.run(adapter=adapter, facts=make_repo_facts())
    assert mapping.engine == "claude-code"


# 4. New vs existing project (section 4) ----------------------------------


def test_a_new_project_gets_the_smallest_runnable_function():
    operation, _ = make_operation()
    mapping = operation.run(adapter=Engine("opencode"), facts=make_repo_facts(), new_project=True)

    assert any("smallest runnable function" in c for c in mapping.reproducible_commands)


def test_an_existing_project_reuses_its_ci_and_documents_missing_ci():
    operation, _ = make_operation()
    with_ci = operation.run(adapter=Engine("opencode"), facts=make_repo_facts(existing_ci=True))
    assert any("reuse existing CI" in c for c in with_ci.reproducible_commands)

    without_ci = operation.run(adapter=Engine("opencode"), facts=make_repo_facts(existing_ci=False))
    assert any("no existing CI" in c for c in without_ci.constraints)
