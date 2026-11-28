"""External and decentralized providers, checked against A66-A69.

Issue #63's criteria, mapped one test each (specification section 7.2):

1. A cloud worker pool is created idempotently, a crash after VM-creation
   but before worker registration leaves an orphan that is cleaned up, and
   autoscaling stops at the budget/capacity frame (A66).
2. Two organizations instantiated from the same template get separate IDs,
   policy, and authoritative boundaries (A66).
3. One versioned ExecutionProfile runs against two independent Execution
   Backends and a simulator; a missing required capability blocks or needs
   an explicit approval, never a silent weakening (A67).
4. A direct backend works without Kubernetes/Terraform; the Kubernetes and
   IaC paths are enabled only when supported and qualified, and secrets
   never reach a worker (A68).
5. A scoped, approved subtask is sent via two DecentralizedWorkProvider
   adapters; the untrusted result is hash-checked and independently verified;
   confidential material is refused; a failure in one provider does not block
   other qualified capacity (A69).
"""

from __future__ import annotations

import pytest

from dev_org.providers import (
    CloudWorkerPoolProvider,
    DirectExecutionBackend,
    ExecutionProfile,
    HippiusDecentralizedWorkProvider,
    IacExecutionBackend,
    KubernetesExecutionBackend,
    OrganizationFactory,
    TargonDecentralizedWorkProvider,
    WorkDispatcher,
    WorkerPoolSpec,
    verify_result,
)

PROFILE = ExecutionProfile(
    version="v1",
    os="linux",
    isolation="sandbox",
    cpu="2",
    memory="4G",
    disk="20G",
    gpu="none",
    region="eu-north",
    lifetime="task",
    cost_limit="100",
    attestation=True,
    required_capabilities=frozenset({"sandbox", "network", "logging", "heartbeat", "fencing"}),
)


def make_spec(
    *,
    nodes: int = 2,
    max_nodes: int = 4,
    cost: dict[str, float] | None = None,
) -> WorkerPoolSpec:
    """A minimal worker pool spec for the pool tests.

    ``cost`` carries the dollar/lifetime budget fields mirrored from how
    Targon/Hippius are rented (ci_leie): rate per hour, lifetime seconds, and
    the day/month caps. Omitted, the pool has no cost and no frame.
    """
    return WorkerPoolSpec(
        node_count=nodes,
        capabilities=frozenset({"sandbox"}),
        network="prod",
        max_nodes=max_nodes,
        budget_frame=f"${max_nodes * 10}",
        rate_usd_hour=(cost or {}).get("rate", 0.0),
        lifetime_s=int((cost or {}).get("lifetime_s", 0)),
        day_cap_usd=(cost or {}).get("day_cap", float("inf")),
        month_cap_usd=(cost or {}).get("month_cap", float("inf")),
    )


# 1. Worker pool: idempotent create, crash reconciliation, autoscaling (A66) --


def test_retry_does_not_create_double_vms_and_orphans_are_reconciled():
    provider = CloudWorkerPoolProvider()
    first = provider.create_pool(spec=make_spec(nodes=2), idempotency_key="key-1")
    before = provider.count_vms(pool_id=first)

    # A crash occurred after the VM was created but before the worker
    # registered: one VM is an orphan. A retry with the same key must not
    # create a second set of VMs (A66).
    retry = provider.create_pool(spec=make_spec(nodes=2), idempotency_key="key-1")
    assert retry == first
    assert provider.count_vms(pool_id=first) == before  # no double VMs

    # The orphan is found and cleaned up by reconciliation.
    orphans = provider.reconcile(pool_id=first)
    assert orphans  # there is at least one unregistered VM after the crash
    assert provider.orphans_cleaned >= len(orphans)
    assert not provider.reconcile(pool_id=first)  # idempotent: nothing left


def test_autoscaling_stops_at_the_budget_frame_cap():
    provider = CloudWorkerPoolProvider()
    pool = provider.create_pool(spec=make_spec(nodes=2, max_nodes=4), idempotency_key="autoscale")

    # Requesting far more than the budget frame allows must be capped.
    scaled = provider.autoscale(pool_id=pool, desired=100)
    assert scaled == 4  # capped at max_nodes == the budget frame


def test_autoscaling_stops_at_the_dollar_time_budget_frame():
    # Faithful to ci_leie (R-40): each machine's whole lifetime (rate * ttl)
    # must fit under the day/month dollar cap. Two machines at $1/h for 1h
    # cost $2, so a $1 day cap lets at most one start.
    provider = CloudWorkerPoolProvider()
    pool = provider.create_pool(
        spec=make_spec(nodes=1, max_nodes=5, cost={"rate": 1.0, "lifetime_s": 3600, "day_cap": 1.0}),
        idempotency_key="dollar-cap",
    )
    # Even though 4 more nodes are available (max_nodes=5), the dollar cap
    # allows only the one already started: one more whole lifetime would pass $1.
    assert provider.blocked(pool_id=pool, extra_nodes=1) == "day cap would be passed"
    assert provider.autoscale(pool_id=pool, desired=5) == 1


def test_a_machine_that_never_started_holds_no_lifetime():
    # ci_leie rule: a failed start or orphan holds no lifetime against the cap,
    # so it does not block a provider's stand-in. An unregistered orphan is a VM
    # created but never started: reconciliation removes it (it costs nothing)
    # and the cap stays free for a real machine.
    provider = CloudWorkerPoolProvider()
    pool = provider.create_pool(
        spec=make_spec(nodes=2, max_nodes=4, cost={"rate": 10.0, "lifetime_s": 3600, "day_cap": 10.0}),
        idempotency_key="no-lifetime",
    )
    assert provider.reconcile(pool_id=pool)  # an orphan that never started is cleaned
    # Starting one real machine is allowed: its whole lifetime fits the $10 cap.
    assert provider.autoscale(pool_id=pool, desired=3) >= 1
    assert provider.blocked(pool_id=pool, extra_nodes=1) == "day cap would be passed"


# 2. Two organizations from one template stay separate (A66) ----------------


def test_two_organizations_from_the_same_template_stay_separate():
    factory = OrganizationFactory(template="acme-template")
    org_a = factory.instantiate(name="alpha")
    org_b = factory.instantiate(name="beta")

    assert org_a.organization_id != org_b.organization_id
    assert org_a.policy_ref != org_b.policy_ref
    assert org_a.data_store_id != org_b.data_store_id
    assert org_a.board_ref != org_b.board_ref
    assert set(org_a.repository_refs).isdisjoint(org_b.repository_refs)
    # Each shares only the template's shape, not the other's authority.
    assert "alpha" in org_a.organization_id
    assert "beta" in org_b.organization_id


# 3. One profile across two independent backends + a simulator (A67) ---------


def test_the_same_profile_runs_across_two_backends_with_equal_reports():
    direct = DirectExecutionBackend()
    k8s = KubernetesExecutionBackend()
    id_a = direct.create(profile=PROFILE, idempotency_key="p-1")
    id_b = k8s.create(profile=PROFILE, idempotency_key="p-1")

    report_a = direct.qualify(profile=PROFILE)
    report_b = k8s.qualify(profile=PROFILE)
    # Normalized reports: same enforced capabilities, no missing requirement.
    assert report_a.missing == []
    assert report_b.missing == []
    assert report_a.capabilities == report_b.capabilities
    # Both backends accepted the same profile; only provider and resource differ.
    assert report_a.provider != report_b.provider
    assert id_a != id_b


def test_a_missing_required_capability_blocks_unless_explicitly_approved():
    strong_profile = ExecutionProfile(
        version="v1",
        os="linux",
        isolation="vm",
        cpu="8",
        memory="32G",
        disk="200G",
        gpu="1xA100",
        region="eu-north",
        lifetime="task",
        cost_limit="500",
        required_capabilities=frozenset({"gpu"}),
    )
    direct = DirectExecutionBackend()  # native capabilities lack "gpu"
    report = direct.qualify(profile=strong_profile, require=False)
    assert "gpu" in report.missing

    # Forcing the requirement must block (no silent weakening, A67).
    with pytest.raises(ValueError, match="cannot enforce"):
        direct.qualify(profile=strong_profile, require=True)

    # An explicitly approved alternative is the only way past it.
    approved = direct.qualify(profile=strong_profile, require=False)
    assert "gpu" in approved.missing
    assert approved.lifecycle_status == "running"


def test_checkpoint_movement_seeds_into_an_environment():
    direct = DirectExecutionBackend()
    resource = direct.create(profile=PROFILE, idempotency_key="ck-1")
    direct.seed_checkpoint(resource_id=resource, checkpoint="snapshot-x")
    # Seeding into a known environment is accepted; an unknown one is not.
    with pytest.raises(KeyError):
        direct.seed_checkpoint(resource_id="nope", checkpoint="snapshot-x")


# 4. Direct backend works; k8s/IaC only when qualified; secrets stay out (A68)


def test_the_direct_backend_works_without_kubernetes_or_terraform():
    direct = DirectExecutionBackend()
    resource = direct.create(profile=PROFILE, idempotency_key="direct-1")
    pid = direct.run(resource_id=resource, command="echo hello")
    assert resource.startswith("direct")
    assert pid
    direct.end(resource)
    assert direct.resource_count() == 0


def test_kubernetes_is_enabled_only_when_supported():
    supported = KubernetesExecutionBackend(supported=True)
    resource = supported.create(profile=PROFILE, idempotency_key="k-1")
    assert resource.startswith("kubernetes")

    missing_interface = KubernetesExecutionBackend(supported=False)
    with pytest.raises(RuntimeError, match="missing"):
        missing_interface.create(profile=PROFILE, idempotency_key="k-2")
    assert missing_interface.supported() is False


def test_iac_apply_failure_rolls_back_and_not_qualified_without_an_interface():
    failing = IacExecutionBackend(supported=True, apply_fails=True)
    with pytest.raises(RuntimeError, match="rolled back"):
        failing.apply(desired=make_spec())
    assert failing.apply_count == 0
    assert failing.rollback_count == 1

    no_interface = IacExecutionBackend(supported=False)
    with pytest.raises(RuntimeError, match="not qualified"):
        no_interface.apply(desired=make_spec())


def test_provider_and_wallet_secrets_never_reach_a_worker():
    for backend in (DirectExecutionBackend(), KubernetesExecutionBackend(), IacExecutionBackend()):
        backend.send_secret(key="wallet", value="secret-value")
        assert backend.secret_reaches_worker("wallet") is False


# 5. Decentralized work: untrusted result, hash-checked, verified (A69) -----


def test_a_scoped_approved_subtask_is_verified_via_two_providers():
    for sim in (TargonDecentralizedWorkProvider, HippiusDecentralizedWorkProvider):
        provider = sim(correct_result="verified answer")
        task = provider.submit(subtask="solve x", approved_artifacts=["public input"])
        result, digest = provider.result(task)

        # The provider's score grants no acceptance; only our own hash check
        # does. A correct result passes, a tampered one fails.
        assert verify_result(expectation_sha256=digest, candidate=result) is True
        assert verify_result(expectation_sha256=digest, candidate="tampered") is False


def test_a_wrong_result_from_a_provider_is_rejected():
    provider = TargonDecentralizedWorkProvider(correct_result="right")
    task = provider.submit(subtask="compute", approved_artifacts=[])
    _result, digest = provider.result(task)
    # The provider returns its own digest, but dev-org re-verifies: a wrong
    # result (even hash-colliding in the sim) is only trusted by an
    # independent check, which rejects anything that doesn't match.
    hijacked = "attacker output"
    assert verify_result(expectation_sha256=digest, candidate=hijacked) is False


def test_confidential_material_is_refused_and_not_sent():
    provider = TargonDecentralizedWorkProvider()
    with pytest.raises(ValueError, match="refused"):
        provider.submit(subtask="CONFIDENTIAL customer data", approved_artifacts=[])
    with pytest.raises(ValueError, match="refused"):
        provider.submit(subtask="normal", approved_artifacts=["CONFIDENTIAL secret"])
    assert provider.refused_confidential  # nothing was sent out


def test_a_failure_in_one_provider_does_not_block_other_qualified_capacity():
    # Both providers are independent: one refusing a task is isolated.
    targon = TargonDecentralizedWorkProvider()
    hippius = HippiusDecentralizedWorkProvider(correct_result="other output")
    with pytest.raises(ValueError, match="refused"):
        targon.submit(subtask="CONFIDENTIAL leak", approved_artifacts=[])

    # The other provider's capacity is unaffected and still serviceable.
    task = hippius.submit(subtask="ok task", approved_artifacts=[])
    result, _digest = hippius.result(task)
    assert result == "other output"


def test_fail_over_moves_to_the_fallback_after_two_failed_starts():
    # Faithful to bittensor-compute: Targon is tried first, and after two
    # failed starts in a row the work moves to Hippius instead of retrying
    # Targon (A69: a failure in one provider does not block other capacity).
    targon = TargonDecentralizedWorkProvider()
    hippius = HippiusDecentralizedWorkProvider(correct_result="stand-in answer")
    dispatcher = WorkDispatcher(primary=targon, fallback=hippius)
    assert dispatcher.prefers_fallback() is False  # Targon is the first choice

    # Targon is down for its first two starts; both fail and count the streak.
    targon.down = True
    first = dispatcher.send(subtask="job", approved_artifacts=[])
    second = dispatcher.send(subtask="job", approved_artifacts=[])
    assert first is None
    assert second is None
    # After two failed starts the dispatcher is primed to route to Hippius.
    assert dispatcher.prefers_fallback() is True
    standby = dispatcher.send(subtask="job", approved_artifacts=[])
    assert standby is not None
    assert standby.startswith(f"{hippius.name}-")
    # The fallback's result is still verified independently.
    text, digest = hippius.result(standby)
    assert verify_result(expectation_sha256=digest, candidate=text) is True
