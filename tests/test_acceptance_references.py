"""Every acceptance-test reference in the specification points at a real test.

The specification's section 12 defines the acceptance tests A01-A79 in a
table, and other places in the document refer to them by ID, often as ranges
("A19-A22"). A reference to a test that no longer exists is a verification
contract that names nothing, and the repository standard is that a rule
states its mechanism: this test is that mechanism for the spec's own
cross-references.

The bootstrap backlog (`.bootstrap/github-backlog.json`) is gitignored, so a
fresh clone does not have it; when the file is present its references are
checked against the same table, and when it is absent that check is skipped.
"""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).parent.parent
SPEC = ROOT / "dev-org-specification.md"
BACKLOG = ROOT / ".bootstrap" / "github-backlog.json"

# A defined test is a row of the acceptance-test table: `| A01 | ... | ... |`.
TABLE_ROW = re.compile(r"^\|\s*(A\d{2})\s*\|")
# Anywhere in the spec, a test may be named alone or as a range "A19-A22".
REFERENCE = re.compile(r"\bA(\d{2})(?:\s*[-\u2013]\s*A(\d{2}))?\b")


def defined_tests() -> set[str]:
    """Every test ID the acceptance-test table defines, in section 12."""
    rows = [TABLE_ROW.match(line) for line in SPEC.read_text().splitlines()]
    return {match.group(1) for match in rows if match}


def references_in(text: str) -> set[str]:
    """Every test ID a piece of text refers to, ranges expanded."""
    found = set()
    for match in REFERENCE.finditer(text):
        start, end = int(match.group(1)), int(match.group(2) or match.group(1))
        if end < start:
            msg = f"backwards range A{start:02d}-A{end:02d}"
            raise ValueError(msg)
        found.update(f"A{n:02d}" for n in range(start, end + 1))
    return found


def test_the_table_defines_every_expected_id():
    """A table that skipped an ID would leave its references pointing at nothing."""
    defined = defined_tests()
    numbers = sorted(int(t[1:]) for t in defined)
    expected = {f"A{n:02d}" for n in range(1, numbers[-1] + 1)}
    assert defined == expected, (
        f"acceptance-test table has gaps: "
        f"missing {sorted(expected - defined)}, extra {sorted(defined - expected)}"
    )


def test_every_reference_in_the_spec_points_at_a_defined_test():
    """A cross-reference to a removed test is a contract that names nothing."""
    text = SPEC.read_text()
    unknown = sorted(references_in(text) - defined_tests())
    assert not unknown, f"specification refers to tests that are not defined: {unknown}"


def test_every_defined_test_is_referenced_somewhere_in_the_spec():
    """An unreferenced test is still a requirement; this catches a removed reference."""
    text = SPEC.read_text()
    orphaned = sorted(defined_tests() - references_in(text))
    assert not orphaned, f"tests defined but never referred to elsewhere: {orphaned}"


def test_the_backlog_references_only_defined_tests():
    """When the local backlog is present, its test references must name real tests.

    Skipped on a fresh clone because `.bootstrap/` is gitignored.
    """
    if not BACKLOG.is_file():
        return
    config = json.loads(BACKLOG.read_text())
    names = " ".join(issue["spec"] for issue in config["issues"])
    unknown = sorted(references_in(names) - defined_tests())
    assert not unknown, f"backlog refers to tests that are not defined: {unknown}"
