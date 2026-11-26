# Agent work in the dev-org repo

These are short, repository-specific working rules. The requirements on architecture, mandates, and delivery are in the [system specification](dev-org-specification.md); the practical workflow is in the [work protocol](docs/development/work-protocol.md).

- Write all content in English: documentation, commit messages, code comments, and replies. English never needs the joined a-e, the slashed o, or the ringed a, and `tests/test_english_only.py` fails a commit that brings one of them into a tracked file. Do not leave a Norwegian phrase behind in a file you touch, even one you did not write.

- State the intent first in every commit message and pull request: what the change is for and where it stood before, in words somebody who has never seen this project could follow. No file name, setting, or abbreviation before that sentence is explained. The `write-commit` skill has the detail; `scripts/readable.py` warns when the body gets hard to read.

- Anchor changes in a backlog issue with acceptance criteria. If the issue is not ready, clarify the criteria, dependencies, or contracts before implementation.
- Read the relevant parts of the specification and map the affected modules, data owners, interfaces, and verification before splitting up or starting parallel work.
- Prefer small, runnable end-to-end deliveries. The MVP is a modular monolith; do not create a new service or abstraction without a documented need and real consumers.
- Do not let concurrent workers edit the same files or change the same contract without coordination. Designate one temporary responsible for a shared contract, agree compatibility and test first, and let others work against the contract with test doubles.
- Use isolated working copies/branches for parallel deliveries. Integrate small changes often, and verify the combination to be merged with the project's documented checks.
- If a dependency, test resource, or interface blocks the work, record the concrete obstruction and propose the smallest clarification. Do not create a competing contract or hide a blockage with a stopgap.
- In the delivery report state the change, the affected contracts, the checks that actually ran, the result, and the remaining risk. Do not claim something is verified without evidence.
- Use the [skill for parallel dev-org work](skills/dev-org-parallel-work/SKILL.md) for tasks across modules or work done at the same time by several agents.
- Use the [skill for documentation maintenance](skills/dev-org-doc-maintenance/SKILL.md) when you change the specification, acceptance requirements, work protocols, or architecture diagrams.
