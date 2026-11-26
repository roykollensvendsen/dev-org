"""Everything in this repository is written in English.

English needs none of the joined a-e, the slashed o, or the ringed a, in
any case. Any of them in a tracked file or filename is therefore a
Norwegian word that slipped through, and the repository standard is that a
rule states its mechanism: this test is the mechanism for the English-only
rule in AGENTS.md and CONTRIBUTING.md.

Files are found by ``git ls-files`` so that only what is actually tracked is
judged: an ignored scratch file (.bootstrap/, a local notes file) does not
need to be in English. A binary file has no text to judge, and a file that
does not decode as UTF-8 is treated as binary.

The pattern is written as escapes so that this very file, which must match
the letters, does not itself carry them: the rule applies even to the test
that enforces it. The same escapes appear in ``scripts/english.py``, which
covers commit messages.
"""

import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).parent.parent
# \u00e6 \u00f8 \u00e5 \u00c6 \u00d8 \u00c5: the three letters English never uses.
NORWEGIAN = re.compile("[\u00e6\u00f8\u00e5\u00c6\u00d8\u00c5]")


def tracked_files() -> list[str]:
    """Every path Git tracks, relative to the repository root, including renames."""
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    return [line for line in result.stdout.splitlines() if line]


def test_no_tracked_filename_contains_norwegian_letters():
    """A path is read by the next person too, so it is content."""
    offending = [path for path in tracked_files() if NORWEGIAN.search(path)]
    assert not offending, "tracked filenames containing Norwegian letters:\n" + "\n".join(offending)


def test_no_tracked_file_content_contains_norwegian_letters():
    """The joined a-e, slashed o, and ringed a are the signal that survives translation."""
    hits: list[str] = []
    for path in tracked_files():
        text = read_text(path)
        if text is None:
            continue  # binary, or not UTF-8: there is no text to judge
        for number, line in enumerate(text.splitlines(), start=1):
            if NORWEGIAN.search(line):
                hits.append(f"{path}:{number}: {line.strip()[:80]}")
    assert not hits, "tracked content containing Norwegian letters:\n" + "\n".join(hits)


def read_text(path: str) -> str | None:
    """The file's text, or None when it is not readable as UTF-8 text."""
    try:
        return (ROOT / path).read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return None
