# Work protocol for parallel development

The protocol makes the rules in sections 4.2 and 6 of the [system specification](../../dev-org-specification.md) applicable in daily work. It applies to humans and agents. The specification is authoritative if the wording differs.

## Clarify the task

Before assignment the issue must have:

- a scoped result and observable acceptance criteria;
- affected components, folders, or contracts per the best-known mapping;
- explicit dependencies and an order where work must actually wait;
- a local verification method, relevant contract/integration checks, and any external test requirements;
- shared or scarce resources that must be reserved.

If a central interface is not yet decided, first create a small clarification task. Do not assign several implementers to each guess their own interface.

## Assign and limit concurrency

- Have one responsible per delivery and one temporary responsible for a contract changed across modules. It is not a permanent approval role.
- Distribute work by module responsibility and dependencies. Gather strongly coupled changes with one worker or in one coordinated delivery.
- Limit active work per module when several changes hit the same files, schema, or test state. Prioritize tasks that free blocked workers.
- Use a separate working copy or git worktree per concurrent delivery. Do not share writable test data or local working copies between parallel runs.
- Reserve physical benches, account/API quotas, and other scarce resources. Use simulators when they cover the same assumptions.

## Agree the contract before parallel implementation

When a public contract must change, designate the responsible for schema/calls, compatibility, failure types, ownership, and contract tests. Publish a small example or test double that consumers can develop against. Prefer compatible introduction: add new support, move consumers, and remove old support afterwards. If that is not possible, coordinate the delivery and test the whole combination before integration.

Do not create a new abstraction just to distribute work. Use existing ports; the MVP runs as a modular monolith with real isolation boundaries for untrusted execution.

## Integrate continuously

- Keep changes small and branches short. Integrate as soon as the acceptance criteria are met.
- Delete the branch after it is merged: locally in the working copy, and on the remote if GitHub has not already removed it. A merged branch left behind is dead weight that the next worker has to tell apart from live work.
- Run relevant component and contract checks early. Run the integration check on the actual combination to be merged; widen the test selection on unknown impact.
- Cancel stale builds and test jobs no consumer needs. Do not let the CI queue or a shared test resource fill with duplicates.
- On conflict, stop overlapping writing, choose one responsible for the merge, and update dependencies. Do not resolve a conflict by overwriting unknown work.
- Report what changed, which contracts are affected, which checks actually ran, the result, and any open blockages.

## Find and remove bottlenecks

Follow at least:

- time from ready issue to start, and wait time on dependencies;
- active WIP per module and issues blocking others;
- merge conflicts, integration failures, and rework per contract/module;
- CI queue time, run time, reused/duplicated checks, and failure rate;
- wait time on scarce workers, test environments, and external quotas.

Use the measurements to reduce WIP, clarify ownership, or improve the relevant boundary/test. Do not increase the number of parallel workers before the observed bottleneck tolerates more work. The number of agents, commits, or open PRs is not in itself a measure of progress.
