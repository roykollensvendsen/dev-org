# dev-org

dev-org is a modular framework for autonomous organizations of coding agents.
It is designed to coordinate agents from different engines through shared tasks,
messages, explicit permissions, and observable work records.

The authoritative requirements are in the
[system specification](dev-org-specification.md). Start with the
[architecture diagrams](docs/architecture/system-diagrams.md) for the
details. The system is not implemented yet; the repository currently contains
the specification, design material, and development scaffolding.

## Development

The chosen implementation baseline is Python 3.14, FastAPI, and Pydantic 2.
The first implementation milestone is a small, runnable end-to-end slice, as
defined by the specification's delivery plan.

The command line exists as a skeleton and does nothing yet:

```console
$ dev-org
dev-org: nothing to do yet
```

<!-- not run: setup instructions for a fresh clone -->
```bash
git clone https://github.com/roykollensvendsen/dev-org.git
cd dev-org
uv sync --all-extras
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the change workflow and CI gates.
The repository-specific agent instructions are in [AGENTS.md](AGENTS.md), and
the detailed work protocol is in
[docs/development/work-protocol.md](docs/development/work-protocol.md).

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).
