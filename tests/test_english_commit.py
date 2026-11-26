r"""What the English-only rule accepts and refuses.

The repository is written in English, and the joined a-e, the slashed o and
the ringed a are the signal that survives translation: English needs none of
them. This script guards commit messages, which never enter a tracked file
and so escape the content scan in test_english_only.py.

The Norwegian examples are written as escapes so that this file stays
all-English: the content scan reads every tracked file, and a rule must not
fail its own test. \\u00f8 is the slashed o and \\u00e5 the ringed a.
"""

import functools
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))

import english

ENGLISH = "docs: Add the check\n\nA body written in English.\n"
NORWEGIAN = "docs: Gj\u00f8r noe p\u00e5 norsk\n"  # contains both the slashed o and the ringed a


def test_an_english_message_is_left_alone():
    assert english.offence(ENGLISH) == []


def test_a_message_with_a_norwegian_letter_is_named():
    said = english.offence(NORWEGIAN)
    assert len(said) == 1
    assert "Gj\u00f8r noe p\u00e5 norsk" in said[0]


def test_a_comment_line_is_not_the_message(tmp_path):
    """Git's editor leaves a comment block above the message; the hook must not read it."""
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("# Please enter the commit message\n\n" + ENGLISH)
    # The blank line after the comments is kept (it is not a comment); the
    # offence check skips it because it has no letters to judge.
    expected = "\n" + ENGLISH.rstrip("\n")
    assert english.from_file(str(message)) == [("COMMIT_EDITMSG", expected)]


def test_the_range_is_read_from_git(tmp_path):
    """A rule that cannot see the commits enforces nothing."""
    run = functools.partial(subprocess.run, cwd=tmp_path, check=True, capture_output=True)
    run(["git", "init", "-q", "-b", "main"])
    run(["git", "config", "user.email", "test@example.com"])
    run(["git", "config", "user.name", "A Test"])
    run(["git", "commit", "-q", "--allow-empty", "-m", "feat: Add the first thing"])
    run(["git", "commit", "-q", "--allow-empty", "-m", "fix: Gj\u00f8r noe p\u00e5 norsk"])

    found = english.messages("HEAD~1..HEAD", cwd=str(tmp_path))
    assert [message for _, message in found] == ["fix: Gj\u00f8r noe p\u00e5 norsk"]


def test_an_empty_message_offends_nothing(tmp_path):
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("# only comments\n")
    assert english.from_file(str(message)) == [("COMMIT_EDITMSG", "")]
    assert english.offence("") == []
