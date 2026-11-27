"""A tracked document must not be a parallel task list in Git.

The specification's section 4 fixes the board as the authoritative home of
tasks, backlog, priority, acceptance criteria, dependencies, and decisions,
and says "No parallel task list in Git." A tracked markdown file that
restates the backlog as a plan — a list of concrete GitHub issues with
their titles and a delivery order — duplicates the board, and the copy
silently drifts when the board changes.

This is the guard for that rule. A document that *mentions* an issue in
prose ("issue #13 delivers handover") is fine; a document that *lists*
issues with a delivery order ("#35 -> #36 -> #37") or a "Part of epic #N"
marker is a parallel task list and fails.

The signature is deliberately narrow so legitimate references in ADRs and
docs pass: at least two GitHub issue numbers joined by an arrow (a
delivery chain), or the "Part of epic #N" marker that ties an issue to an
epic on the board.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).parent.parent

#: Every tracked markdown file (excluding the spec and the skills, which are
#: content, not backlog plans).
TRACKED_MD = sorted(path for path in (ROOT / "docs").rglob("*.md") if "architecture" not in path.parts)
TRACKED_MD += sorted((ROOT / "decisions").glob("*.md"))

#: A delivery chain: two or more issue numbers joined by "->" or "→",
#: e.g. "#35 -> #36 -> #37". This is the signature of a restated plan.
CHAIN = re.compile(r"#\d+\s*(?:->|→)\s*#\d+")
#: The marker an issue uses on the board to name its epic.
EPIC_MARKER = re.compile(r"Part of epic #\d+")


def test_tracked_docs_do_not_restate_the_backlog_as_a_plan():
    """A delivery chain or epic marker in a tracked doc is a parallel list."""
    offenders: list[str] = []
    for path in TRACKED_MD:
        text = path.read_text()
        if CHAIN.search(text) or EPIC_MARKER.search(text):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        "tracked documents restate the backlog as a plan (spec section 4: "
        "no parallel task list in Git): " + ", ".join(offenders)
    )


def test_the_signature_is_specific_not_overbroad():
    """Prose that merely mentions an issue must not trip the guard.

    An ADR saying "issue #13 delivers handover" or a doc describing a
    decision is legitimate; only the chain or epic-marker signatures are
    flagged. This pins the regexes so a future loosening cannot silently
    widen the guard.
    """
    assert CHAIN.search("Deliver #35 -> #36 first")  # a real chain
    assert not CHAIN.search("issue #13 delivers handover")  # prose only
    assert EPIC_MARKER.search("Part of epic #14")  # the board marker
    assert not EPIC_MARKER.search("the epic in #14")  # prose only
