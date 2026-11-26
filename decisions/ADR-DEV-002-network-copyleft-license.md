# ADR-DEV-002: Use a network copyleft license

## Status

Accepted. Decided by the project owner on 2026-11-26.

## Context

dev-org is intended to run as a networked service and the project owner wants
improvements to remain available to users. Apache-2.0 allows redistribution of
modified versions without requiring those changes to be shared. GPL-3.0 adds
source-sharing requirements when modified copies are conveyed, but does not
cover changes used only through a network service. AGPL-3.0 adds a source offer
for users interacting remotely with a modified version.

## Options considered

- Apache-2.0: broad adoption and patent terms, but no obligation to share
  modifications.
- GPL-3.0-or-later: copyleft when modified copies are conveyed, but not for
  modified versions used only as a network service.
- AGPL-3.0-or-later: copyleft on conveyed copies and a source offer to users of
  modified network versions; this may make some organizations more cautious
  about adoption.

## Decision

License dev-org under AGPL-3.0-or-later. This aligns source availability with
the planned networked deployment model. It does not require users to submit
their changes as patches to this repository; forks remain allowed under the
license terms.

## Consequences

Users of a modified network deployment must be offered its corresponding
source under the license. Organizations may be more cautious about adopting or
integrating AGPL software. Contributions accepted here use the same license;
this project does not require copyright assignment or a separate contributor
agreement.

## Related

- [GNU AGPLv3](https://www.gnu.org/licenses/agpl-3.0.html)
- [GNU GPL FAQ: web server modifications](https://www.gnu.org/licenses/gpl-faq.html#UnreleasedMods)
- [README](../README.md)
- [Contributor guide](../CONTRIBUTING.md)
