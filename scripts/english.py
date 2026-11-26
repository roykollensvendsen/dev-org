#!/usr/bin/env python3
"""Refuse a commit message that carries a letter English never uses.

The repository is written in English, by AGENTS.md and CONTRIBUTING.md, and
the joined a-e, the slashed o and the ringed a are the signal that survives
translation: English needs none of them, so any of them in a commit message
is a Norwegian word that slipped through. The content scan,
tests/test_english_only.py, covers tracked files; this covers the message
itself, which never enters a file.

    python scripts/english.py origin/main..HEAD
    python scripts/english.py --all
    python scripts/english.py --file .git/COMMIT_EDITMSG

The second form is what the commit-msg hook uses, so a message is refused
while it is being written rather than in CI afterwards. Exit 1 names every
line that offends.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

#: The letters English never needs, in both cases. Written as escapes so that
#: this file stays all-English: the content scan in tests/test_english_only.py
#: reads every tracked file, and a pattern must not fail itself.
NORWEGIAN = re.compile("[\u00e6\u00f8\u00e5\u00c6\u00d8\u00c5]")


def offence(message: str) -> list[str]:
    """The message's lines that carry a forbidden letter, or an empty list."""
    return [line.strip() for line in message.splitlines() if NORWEGIAN.search(line)]


def from_file(path: str) -> list[tuple[str, str]]:
    """The message being written, minus its comment lines, as the hook sees it."""
    kept = [line for line in pathlib.Path(path).read_text().splitlines() if not line.strip().startswith("#")]
    return [(pathlib.Path(path).name, "\n".join(kept))]


def messages(commit_range: str, cwd: str | None = None) -> list[tuple[str, str]]:
    """Every commit in the range, as its short hash and its full message.

    ``cwd`` exists so a test can build its own history and read that, rather
    than reading whatever the checkout happens to be. It is never passed in
    normal use.
    """
    result = subprocess.run(  # noqa: S603
        ["git", "log", "--no-merges", "--format=%h%x00%B%x01", commit_range],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
        cwd=cwd,
    )
    out = []
    for chunk in result.stdout.split("\x01"):
        if "\x00" in chunk:
            sha, message = chunk.strip().split("\x00", 1)
            out.append((sha[:7], message))
    return out


def main() -> int:
    """Check a message file, every commit, a range, or the last commit."""
    if len(sys.argv) > 2 and sys.argv[1] == "--file":  # noqa: PLR2004
        where = sys.argv[2]
        pairs = from_file(where)
    elif sys.argv[1:2] == ["--all"]:
        # Not root..HEAD: a range excludes its own start, so asking for the
        # whole history that way silently skips the first commit.
        where = "every commit"
        pairs = messages("HEAD")
    else:
        where = sys.argv[1] if len(sys.argv) > 1 else "HEAD~1..HEAD"
        pairs = messages(where)
    found = [(name, line) for name, message in pairs for line in offence(message)]
    for name, line in found:
        print(f"{name}: {line[:80]}")  # noqa: T201
    if not found:
        print(f"Every message in {where} is written in English.")  # noqa: T201
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
