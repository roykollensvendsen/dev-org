<!-- Five parts, in this order. The `write-commit` skill has the detail.

     Write for somebody who has never seen this project. They do not know the
     file names, the settings or what any abbreviation here stands for, and they
     should not have to open the code to follow you. Everyday words. Explain a
     term before you lean on it, and never open on jargon.

     1. Intent: what this part is for, and where it stood before.
     2. What changed, and why this way rather than another way.
     3. What a reviewer should push on: the weakest parts of your own change.
     4. Testing done: the commands you actually ran and what they showed beyond
        what CI reports on its own — the new tests by name, that they were red
        before the code turned them green, and anything skipped and why.
     5. The details, for whoever maintains this: file names, settings, flags,
        record numbers — gathered here so everything above can be read without
        them.
     6. The checklist below.

     Leave out what CI already reports on this page. -->

## Testing done

<!-- What CI already shows (lint, format, type, and the suite result) belongs
     here only in one line; the value is what CI cannot see:

     - the names of the new tests and that each was red before the code that
       turned it green, with the red run recorded under evidence/tests/;
     - the commands you actually ran, not just the CI pipeline;
     - anything skipped or not run (live engines, Podman, a real board) and why,
       so nobody mistakes a skip for a pass. -->

- New tests: <names; each seen red before green>
- Commands run: <e.g. `uv run python -m pytest tests/test_x.py -q`, then the full suite>
- Skipped / not run: <live tests, engines, or hardware absent here; why>
- Suite result: <one line; the rest CI shows>

## The rules no script can measure

- [ ] The PR opens with the intent: what this change is for and where it stood
      before, in words somebody who has never seen this project could follow.
      Everything above the details section states that intent and what changed,
      without requiring a file name, setting or abbreviation to be explained.
- [ ] The PR body ends with a `Closes #N` line naming the issue it delivers, so
      GitHub links the two and closes the issue on merge. A `closes #3` in the
      title alone does nothing.
- [ ] Every rule this change adds names the check, CI job or review step that
      enforces it, or says plainly that it is not enforced yet and when it will be.
- [ ] The specification changed before the code, or this change only implements
      a line that was already there.
- [ ] Every new test was seen red before the code that turns it green, or the
      rule it guards was turned off and the test was seen red that way, with the
      run recorded under `evidence/tests/`.
- [ ] The `Testing done` section names the new tests, the commands actually
      run, and anything skipped and why — what CI cannot show on its own.
- [ ] A decision that costs more to reverse than to take is a record under
      `decisions/`, linked here.
- [ ] Nothing here copies text that lives somewhere else; it links to it instead.
- [ ] A lesson this change taught is written where the next person doing this
      task will read it: a test or a check where the mistake is checkable, a
      skill or a rule where it is not. Not only in the commit message.
