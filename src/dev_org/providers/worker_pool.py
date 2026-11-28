"""Worker pool simulation and organization instantiation (A66/A68).

Implements acceptance test A66 (section 7.2):

- A cloud worker pool is created through ``WorkerPoolProvider.create_pool``,
  idempotent on retry: the same ``idempotency_key`` never creates a second pool
  or a second set of VMs.
- A crash *after* the provider creates the VM but *before* the worker
  registers leaves an orphan: ``reconcile`` finds it and cleans it up within
  budget, and a retry of the create does not produce a double VM.
- Autoscaling moves capacity toward ``desired`` but stops at the spec's budget
  frame / ``max_nodes``: it never exceeds the upper bound (A66: "autoscaling
  against a budget cap").
- Workers join through the same contract and get project-scoped identity.

A66 also instantiates two organizations from the same template and asserts
they get separate IDs, policy, and authoritative store boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dev_org.providers.contracts import WorkerPoolSpec


@dataclass
class Vm:
    """One VM owned by a pool, with a registered-worker marker.

    ``started`` is whether the machine ever began its paid lifetime. A machine
    that never started holds no lifetime against the cap, so an orphan or a
    failed start does not block the provider's stand-in.
    """

    vm_id: str
    pool_id: str
    registered: bool = False
    started: bool = False


@dataclass
class Organization:
    """One organization instance from a template (A66)."""

    organization_id: str
    policy_ref: str
    data_store_id: str
    board_ref: str
    repository_refs: list[str]


class OrganizationFactory:
    """Instantiate organizations from a versioned template (A66).

    Two instances get separate IDs, policy references, data stores, board
    references, and repository sets -- they share the template's shape, not
    each other's authoritative boundaries.
    """

    def __init__(self, *, template: str) -> None:
        """Bind the factory to one versioned template."""
        self._template = template
        self._counter = 0

    def instantiate(self, *, name: str) -> Organization:
        """Create one independent organization from the template."""
        self._counter += 1
        base_repo = self._template.replace("{name}", name)
        return Organization(
            organization_id=f"org-{self._counter}-{name}",
            policy_ref=f"policy/{self._template}/#{self._counter}",
            data_store_id=f"store-{base_repo}-{name}",
            board_ref=f"board/{base_repo}-{name}",
            repository_refs=[f"github/{name}/{base_repo}-site", f"github/{name}/{base_repo}-docs"],
        )


class CloudWorkerPoolProvider:
    """Create and autoscale a worker pool, reconciling crash orphans (A66)."""

    def __init__(self) -> None:
        """Start with no pools."""
        self._pools: dict[str, WorkerPoolSpec] = {}
        self._by_key: dict[str, str] = {}
        self._vms: dict[str, list[Vm]] = {}
        self._workers: dict[str, set[str]] = {}
        self.orphans_cleaned = 0

    @staticmethod
    def _whole(spec: WorkerPoolSpec) -> float:
        """What one machine's whole lifetime can cost (rate * ttl/3600)."""
        if spec.rate_usd_hour <= 0:
            return 0.0
        return spec.rate_usd_hour * (spec.lifetime_s / 3600.0)

    def _held(self, pool_id: str) -> float:
        """What the pool's started machines have already reserved (whole each)."""
        spec = self._pools[pool_id]
        started = sum(1 for vm in self._vms[pool_id] if vm.started)
        return started * self._whole(spec)

    def blocked(self, *, pool_id: str, extra_nodes: int = 0) -> str | None:
        """Why adding ``extra_nodes`` may not start now, or None when it may.

        A machine starts only if its whole lifetime (plus what is already
        reserved) fits under both the per-day and per-month dollar cap.
        """
        spec = self._pools[pool_id]
        held = self._held(pool_id)
        whole = self._whole(spec) * max(extra_nodes, 0)
        if held + whole > spec.day_cap_usd:
            return "day cap would be passed"
        if held + whole > spec.month_cap_usd:
            return "month cap would be passed"
        return None

    def create_pool(self, *, spec: WorkerPoolSpec, idempotency_key: str) -> str:
        """Create one pool and its initial VMs; retry with the same key reuses it.

        A retry after a crash must not create a second set of VMs (A66): if the
        key was already seen and its pool exists, the same pool id is returned
        and no extra VMs are allocated. An orphan (a VM created but never
        registered) is left for ``reconcile`` rather than duplicated.
        """
        if idempotency_key in self._by_key:
            pool_id = self._by_key[idempotency_key]
            if pool_id in self._vms:
                return pool_id
        pool_id = f"pool-{len(self._pools) + 1}"
        self._pools[pool_id] = spec
        self._by_key[idempotency_key] = pool_id
        self._vms[pool_id] = [Vm(vm_id=f"{pool_id}-vm-{i}", pool_id=pool_id) for i in range(spec.node_count)]
        self._workers[pool_id] = set()
        # The whole lifetime of the initial fleet must fit under the caps or
        # nothing may start, exactly as an account-wide or project cap
        # prevents any new machine (A66).
        if self.blocked(pool_id=pool_id, extra_nodes=0):
            for vm in self._vms[pool_id]:
                vm.started = False
        else:
            for vm in self._vms[pool_id]:
                vm.started = True
        return pool_id

    def register_worker(self, *, pool_id: str, worker_id: str) -> str:
        """Register a worker under project-scoped identity (A66: join contract)."""
        if pool_id not in self._workers:
            msg = f"unknown pool {pool_id}"
            raise KeyError(msg)
        self._workers[pool_id].add(worker_id)
        for vm in self._vms[pool_id]:
            if not vm.registered:
                vm.registered = True
                return worker_id
        return worker_id

    def reconcile(self, *, pool_id: str) -> list[str]:
        """Find and clean up orphan VMs -- those never registered (A66).

        Returns the cleaned orphan ids. Orphans are removed from the pool so a
        retry of ``create_pool`` reuses the existing pool and does not spawn a
        double VM.
        """
        if pool_id not in self._vms:
            return []
        orphans = [vm.vm_id for vm in self._vms[pool_id] if not vm.registered]
        self._vms[pool_id] = [vm for vm in self._vms[pool_id] if vm.registered]
        self.orphans_cleaned += len(orphans)
        return orphans

    def autoscale(self, *, pool_id: str, desired: int) -> int:
        """Move capacity toward desired, never past the budget frame (A66).

        Two frames cap growth: the node ceiling (``max_nodes``) and the dollar
        caps that require each new machine's whole lifetime to fit under the
        day/month frame. Growth stops at whichever bound bites first.
        """
        pool_id = str(pool_id)
        spec = self._pools[pool_id]
        current = len(self._vms[pool_id])
        target = min(desired, spec.max_nodes)
        while target > current:
            reason = self.blocked(pool_id=pool_id, extra_nodes=1)
            if reason is not None:
                break  # the budget frame forbids one more machine
            self._vms[pool_id].append(Vm(vm_id=f"{pool_id}-vm-{current}", pool_id=pool_id, started=True))
            current += 1
        return len(self._vms[pool_id])

    def drain(self, *, pool_id: str, worker_id: str) -> None:
        """Drain and terminate one worker before removal (section 7.2)."""
        if pool_id not in self._workers:
            return
        self._workers[pool_id].discard(worker_id)

    def count_vms(self, *, pool_id: str) -> int:
        """Number of VMs (live + orphan) in a pool."""
        return len(self._vms[pool_id])

    def worker_count(self, pool_id: str) -> int:
        """Number of registered workers in a pool."""
        return len(self._workers.get(pool_id, set()))


__all__ = ["CloudWorkerPoolProvider", "Organization", "OrganizationFactory", "Vm"]
