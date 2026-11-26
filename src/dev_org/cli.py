"""Command line for dev-org."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

#: Every verb this command has. The documentation test requires each one to
#: appear in a worked example, so a verb cannot be added without one.
COMMANDS: tuple[str, ...] = ("check", "init")


def init(args: argparse.Namespace) -> int:
    """Map the repo, CI, board, and resources; establish project links."""
    del args  # the startup contract is issue #4; arguments will be added with it
    print("dev-org init: not implemented yet; issue #4 defines the startup contract")  # noqa: T201
    return 0


def check(args: argparse.Namespace) -> int:
    """Run the repository's fast checks: the same lines CI runs."""
    del args
    gates = ["uv run ruff check . && uv run ruff format --check .", "uv run mypy src"]
    # When this command runs inside pytest (a documented-command test calls
    # it), running pytest again would recurse into the very test that called
    # us. So the pytest gate is added only outside a test run.
    if "PYTEST_CURRENT_TEST" not in os.environ:
        gates.append("uv run pytest -q")
    for gate in gates:
        result = subprocess.run(gate, shell=True, capture_output=True, text=True, check=False)  # noqa: S602
        if result.returncode:
            print("checks failed; run the gates to see the errors")  # noqa: T201
            return 1
    print("All checks passed!")  # noqa: T201
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch. Returns a process exit code."""
    parser = argparse.ArgumentParser(prog="dev-org", description=__doc__)
    if COMMANDS:
        parser.add_argument("command", nargs="?", choices=COMMANDS)
    args = parser.parse_args(argv)
    if args.command == "check":
        return check(args)
    if args.command == "init":
        return init(args)
    sys.stdout.write("dev-org: nothing to do yet; try 'dev-org check' or 'dev-org init'\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
