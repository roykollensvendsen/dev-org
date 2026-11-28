"""Provider contracts: profiles, execution backends, worker pools, decentralized work.

Implements issue #63 (acceptance tests A66-A69, specification section 7.2).

Section 7.2 is explicit that dev-org reuses existing platforms rather than
building its own cloud provisioner or compute marketplace, and that new
execution backends are added only on a documented need. This module defines
the provider-neutral contracts behind which concrete providers sit, plus
in-memory simulators used to make the acceptance tests deterministic:

- ``ExecutionProfile`` is versioned and provider-neutral, with desired
  resources, isolation, region, cost limit, and required capabilities
  (A67/A68).
- ``ExecutionBackend`` creates, inspects, connects to, runs on, checkpoints,
  and ends sandboxes/VMs (A67/A68).
- ``WorkerPoolProvider`` creates and operates a fleet of worker nodes when
  the platform does not offer this as a managed function; it autoscales
  within a budget/capacity frame and reconciles orphans (A66/A68).
- ``DecentralizedWorkProvider`` receives scoped, approved subtasks; its
  result is untrusted until hash-checked and independently verified (A69).

Provider, wallet, and subscription secrets stay in the adapter's secrets
boundary and never reach a worker. Nothing here touches a Bittensor chain,
subnet, miner/validator identity, or token economy: those belong behind the
provider adapter, never in the core's task or policy format (section 7.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ExecutionProfile:
    """What an execution environment must be able to enforce (section 7.2).

    The profile is provider-neutral and versioned. ``required_capabilities``
    names things the backend must enforce or measure; the adapter reports
    each one, and a missing requirement blocks unless an alternative is
    explicitly approved (never a silent weakening).
    """

    version: str
    os: str
    isolation: str  # e.g. "sandbox", "vm"
    cpu: str
    memory: str
    disk: str
    gpu: str
    region: str
    lifetime: str
    cost_limit: str
    attestation: bool = False
    required_capabilities: frozenset[str] = frozenset()


@dataclass
class CapabilityReport:
    """What an adapter can actually enforce, with cost and lifecycle status."""

    provider: str
    capabilities: dict[str, bool]
    missing: list[str]
    cost: str
    lifecycle_status: str
    region: str
    isolation: str


@dataclass(frozen=True)
class WorkerPoolSpec:
    """Desired worker pool capacity and its cost frame (section 7.2).

    Mirrors the survivor-agent cost axioms (R-40, ci_leie): a machine may
    start only when its whole lifetime fits under both the per-day and the
    per-month dollar cap, and a machine that never started holds no lifetime.
    ``rate_usd_hour`` and ``lifetime_s`` are the per-worker cost model;
    ``day_cap_usd`` and ``month_cap_usd`` are the budget frame that
    autoscaling and creation must never pass (A66).
    """

    node_count: int
    capabilities: frozenset[str]
    network: str
    max_nodes: int
    budget_frame: str  # an upper bound; autoscaling must never exceed it
    # -- cost model, faithful to how Targon/Hippius are rented --
    rate_usd_hour: float = 0.0
    lifetime_s: int = 0
    day_cap_usd: float = float("inf")
    month_cap_usd: float = float("inf")


class _SecretsBoundary:
    """Holds provider/wallet secrets without ever exposing them to a worker."""

    def __init__(self) -> None:
        """Start with an empty boundary."""
        self._secrets: dict[str, str] = {}

    def store(self, *, key: str, value: str) -> None:
        """Put a secret into the adapter's boundary."""
        self._secrets[key] = value

    def expose(self, secret_key: str) -> str | None:
        """Return a secret to the adapter's own control plane only."""
        return self._secrets.get(secret_key)

    def contains(self, key: str) -> bool:
        """Whether the named secret is held here."""
        return key in self._secrets


@runtime_checkable
class ExecutionBackend(Protocol):
    """Create, inspect, run on, checkpoint, and end sandboxes/VMs (section 7.2)."""

    def create(self, *, profile: ExecutionProfile, idempotency_key: str) -> str:
        """Create an environment; retry with the same key returns the same one."""
        ...

    def describe(self, resource_id: str) -> CapabilityReport:
        """Report what this environment can enforce, with cost and status."""
        ...

    def run(self, *, resource_id: str, command: str) -> str:
        """Run a command inside the environment and return a process id."""
        ...

    def seed_checkpoint(self, *, resource_id: str, checkpoint: str) -> None:
        """Restore a checkpoint from an existing instance."""
        ...

    def end(self, resource_id: str) -> None:
        """End and clean up an environment, idempotently."""
        ...


@runtime_checkable
class WorkerPoolProvider(Protocol):
    """Create and operate worker nodes when the platform lacks a managed pool."""

    def create_pool(self, *, spec: WorkerPoolSpec, idempotency_key: str) -> str:
        """Create a pool; retry with the same key returns the same pool."""
        ...

    def join(self, *, pool_id: str, worker_id: str) -> str:
        """Register a worker under project-scoped identity; return its id."""
        ...

    def autoscale(self, *, pool_id: str, desired: int) -> int:
        """Adjust toward desired capacity, capped by the spec's budget frame."""
        ...

    def drain(self, *, pool_id: str, worker_id: str) -> None:
        """Drain and terminate one worker before it is removed."""
        ...


@runtime_checkable
class DecentralizedWorkProvider(Protocol):
    """Receive scoped, approved subtasks from a decentralized network (section 7.2)."""

    def submit(self, *, subtask: str, approved_artifacts: list[str]) -> str:
        """Submit a scoped subtask; return a provider task id."""
        ...

    def result(self, task_id: str) -> tuple[str, str]:
        """Return the provider's (result, sha256) pair, still untrusted."""
        ...


#: Default capability names used by the sim adapters.
DEFAULT_CAPABILITIES = frozenset({"sandbox", "network", "logging", "heartbeat", "fencing"})

__all__ = [
    "DEFAULT_CAPABILITIES",
    "CapabilityReport",
    "DecentralizedWorkProvider",
    "ExecutionBackend",
    "ExecutionProfile",
    "WorkerPoolProvider",
    "WorkerPoolSpec",
    "_SecretsBoundary",
]
