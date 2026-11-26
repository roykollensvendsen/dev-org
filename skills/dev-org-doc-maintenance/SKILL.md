---
name: dev-org-doc-maintenance
description: Maintain dev-org's specification, acceptance criteria, operational documentation, and architecture diagrams as one consistent source set. Use for documentation or diagram changes in this repository, not for ordinary code-only work.
---

# Maintain dev-org documentation

Keep requirements, acceptance evidence, and diagrams consistent. The system specification is authoritative for system behavior; architecture diagrams are derived views and must not introduce new behavior or permissions.

## Before editing

1. Read the relevant section of [the system specification](../../dev-org-spesifikasjon.md), [system diagrams](../../docs/architecture/system-diagrams.md), and any linked operational protocol.
2. Identify whether the change is normative (changes what the system must do), operational guidance, or explanatory visualization. Put each fact in its authoritative location and link to it instead of copying it.
3. Find all affected references, acceptance cases, and diagram sources. Preserve the decisions and vocabulary already established unless the requested change explicitly revises them.

## Update coherently

- For a normative change, update the specification and a relevant acceptance case in the same change. Increment the specification version when its normative requirements or MVP decisions change.
- Update diagrams when they explain an affected boundary, decision, or data flow. Keep diagram labels short and move detail into adjacent prose. A diagram should make one distinction or flow clear and should not duplicate another view without a clear reason.
- Treat Mermaid and PlantUML files as source. Regenerate checked-in SVGs from PlantUML after changing `.puml`; inspect the rendered image when possible.
- Keep component and port boundaries consistent: ports stay on module edges, inputs and outputs retain their visual convention, and the established top-to-bottom overview remains readable.
- In Mermaid labels, avoid syntax-sensitive punctuation such as semicolons. Keep fenced blocks balanced and use real line breaks or renderer-supported labels rather than literal escaped `\n` text.
- Keep local links valid and use the repository's Norwegian terminology consistently.

## Verify and report

Check that every changed local link resolves, specification references point to the correct sections, and changed diagrams render in the available viewer. If a renderer is unavailable, state that limitation and perform a source-level syntax review. Do not claim tests, rendering, or visual inspection that did not happen. Summarize which source documents changed and any unresolved specification decision.

The repo's [parallel work protocol](../../docs/development/work-protocol.md) describes ownership and integration when documentation edits overlap.
