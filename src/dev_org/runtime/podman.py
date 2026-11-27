"""Execution environment over rootless Podman.

The rootless Podman backend for issue #7, implementing the
``ExecutionBackend`` contract from section 3.3: create, inspect, and end
isolated runs, with an explicit profile for workspace, mounts, network,
CPU, memory, processes, and runtime.

Isolation follows the specification: no general access to the home
directory, other tasks, administrative sockets, or control state; network
off by default; rootfs read-only; no-new-privileges. Rootless Podman
shares the host kernel and is not presented as strong isolation against a
kernel attack (section 10.5) — the pilot's threat model is agent actions,
not hostile kernels.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

#: Keys a profile may set, and what each must be. Unknown keys are refused so
#: a typo cannot silently weaken isolation.
PROFILE_KEYS = {
    "workspace": str,
    "image": str,
    "network": bool,
    "cpu_limit": str,
    "memory_limit": str,
    "pids_limit": int,
    "read_only_rootfs": bool,
    "cap_drop_all": bool,
    "no_new_privileges": bool,
}


@dataclass
class RuntimeProfile:
    """An explicit, validated profile for one run (section 3.3)."""

    workspace: str
    image: str
    network: bool = False
    cpu_limit: str = "1"
    memory_limit: str = "512m"
    pids_limit: int = 128
    read_only_rootfs: bool = True
    cap_drop_all: bool = True
    no_new_privileges: bool = True
    extra: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, profile: dict[str, object]) -> RuntimeProfile:
        """Build and validate a profile; an unknown key is a concrete refusal.

        A missing capability is a blockage, not a silent weakening (A21):
        if the profile asks for something this backend cannot enforce, the
        profile is rejected rather than run weaker.
        """
        unknown = set(profile) - set(PROFILE_KEYS)
        if unknown:
            msg = f"profile asks for keys this backend cannot enforce: {sorted(unknown)}"
            raise ValueError(msg)
        values: dict[str, object] = {}
        for key, kind in PROFILE_KEYS.items():
            if key in profile:
                value = profile[key]
                if not isinstance(value, kind):
                    msg = f"profile key {key} must be {kind.__name__}, got {type(value).__name__}"
                    raise TypeError(msg)
                values[key] = value
            elif key in ("workspace", "image"):
                msg = f"profile requires {key}"
                raise ValueError(msg)
        return cls(**values)  # type: ignore[arg-type]


class PodmanBackend:
    """Create, inspect, and end rootless Podman containers."""

    def __init__(self, *, command: str = "podman") -> None:
        """Bind the backend to the podman command."""
        self.command = command

    def _run(self, args: list[str]) -> str:
        """Run a podman command and return its stdout, raising on failure."""
        result = subprocess.run(  # noqa: S603
            [self.command, *args], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()

    def create(self, profile: dict[str, object]) -> str:
        """Create a container from a validated profile and return its ID."""
        rt = RuntimeProfile.from_mapping(profile)
        run_args: list[str] = ["run", "--detach", "--name", self._name(rt.workspace)]
        run_args += ["--volume", f"{rt.workspace}:/workspace:Z"]
        run_args += ["--network", "none" if not rt.network else "default"]
        run_args += ["--cpus", rt.cpu_limit, "--memory", rt.memory_limit, "--pids-limit", str(rt.pids_limit)]
        if rt.read_only_rootfs:
            run_args += ["--read-only"]
        if rt.cap_drop_all:
            run_args += ["--cap-drop", "ALL"]
        if rt.no_new_privileges:
            run_args += ["--security-opt", "no-new-privileges"]
        run_args += [rt.image, "sleep", "infinity"]
        return self._run(run_args)

    def inspect(self, runtime_id: str) -> dict[str, object]:
        """Report the container's state and resource use as JSON."""
        raw = self._run(["inspect", runtime_id, "--format", "{{json .State}}"])
        parsed: object = json.loads(raw)
        if not isinstance(parsed, dict):
            msg = f"expected a JSON object from podman inspect, got {type(parsed).__name__}"
            raise TypeError(msg)
        return parsed

    def exec_(self, runtime_id: str, command: list[str]) -> str:
        """Run a command inside the container and return its stdout.

        Used by the contract tests to probe the sandbox boundaries (A20).
        """
        return self._run(["exec", runtime_id, *command])

    def end(self, runtime_id: str) -> None:
        """Stop and remove the container, confirming it has stopped."""
        self._run(["stop", "--time", "5", runtime_id])
        self._run(["rm", "--force", runtime_id])

    def _name(self, workspace: str) -> str:
        """A stable, filesystem-safe container name from the workspace path."""
        return "devorg-" + Path(workspace).name.replace("_", "-")
