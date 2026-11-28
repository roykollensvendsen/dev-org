"""Architecture guard: concrete adapters live in gateway/ or agents/, never in core/.

The A2A adapter was first written into core/extensions.py because it shared
an issue with the extension lifecycle; that was a delivery convenience, not
an architecture decision. A concrete adapter talks to something outside the
core (a board, an external agent, an engine) and belongs with the other
adapters: gateway/ for external side effects, agents/ for engines. core/
holds lifecycle and policy services.

core/ may still define adapter *ports* — abstract Protocol definitions that
name what an external adapter must offer, such as the CI status contract in
ci_waiting.py (CiAdapter) and the startup surface in startup.py
(StartupAdapter). The concrete engines implement those ports from agents/.
This test therefore flags a class in core/ whose name ends in ``Adapter``
or ``Client`` and that is not declared as a Protocol.

This test is the mechanism for the rule "concrete adapters live outside
core".
"""

from __future__ import annotations

import pathlib
import re

from dev_org.agents import CodexAdapter
from dev_org.core import ExtensionLifecycle
from dev_org.gateway import A2AAdapter, GitHubAdapter, RedmineAdapter

ROOT = pathlib.Path(__file__).parent.parent
CORE = ROOT / "src" / "dev_org" / "core"

#: A class declaration whose name ends in Adapter or Client.
#: Group 1 is the name. The whole match covers the rest of the declaration
#: line so we can decide from the full declaration whether it is a Protocol.
ADAPTER_CLASS = re.compile(r"^class ([A-Za-z0-9_]+(?:Adapter|Client))\b(.*)$", re.MULTILINE)


def test_no_concrete_adapter_classes_live_in_the_core_module():
    """A concrete adapter in core/ is a placement mistake, not a capability.

    Protocol ports may stay (StartupAdapter, CiAdapter); a concrete adapter
    — like the A2A adapter that started this guard — belongs in gateway/ or
    agents/.
    """
    offenders: list[str] = []
    for path in CORE.glob("*.py"):
        for name, rest in ADAPTER_CLASS.findall(path.read_text()):
            if "Protocol" not in rest:
                offenders.append(f"{path.name}:{name}")
    assert not offenders, (
        "concrete adapters live in gateway/ or agents/, not core/ (an adapter "
        "talks to something outside the core): " + ", ".join(offenders)
    )


def test_the_guard_recognizes_real_adapter_names():
    """Pin the signature so a loosening cannot silently widen the rule."""
    for cls in (A2AAdapter, GitHubAdapter, RedmineAdapter, CodexAdapter):
        assert ADAPTER_CLASS.match(f"class {cls.__name__}") is not None
    # A lifecycle service must not be flagged.
    assert ADAPTER_CLASS.match(f"class {ExtensionLifecycle.__name__}") is None
