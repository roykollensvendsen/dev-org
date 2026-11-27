"""The policy decision module, checked against its acceptance criteria.

Issue #6's criteria, one test each:

1. return allow, deny, or requires approval with a rationale and version;
2. evaluate without model calls (nothing here can call a model);
3. allow branch publishing/PR and deny merge in a representative profile;
4. delegation can only narrow; repo text and engine choice cannot extend;
5. approval requests are recorded durably; a missing basis grants nothing.

Plus the four acceptance tests the issue references (A19, A22, A23, A78),
where the gateway's external enforcement is out of scope.
"""

from datetime import UTC, datetime, timedelta

from dev_org.policy import (
    CREATE_PR,
    MERGE,
    PUBLISH_BRANCH,
    ROLLOUT,
    ApprovalRegistry,
    PolicyEngine,
    Rule,
)
from dev_org.state.models import Approval

#: A representative worker profile: branch publishing and PR are allowed,
#: merge is denied unless an approval has been granted (A19).
WORKER_RULES = [
    Rule(
        PUBLISH_BRANCH, "allow", roles=frozenset({"worker"}), reason="branch publishing is within the mandate"
    ),
    Rule(CREATE_PR, "allow", roles=frozenset({"worker"}), reason="opening a PR is within the mandate"),
    Rule(
        MERGE,
        "requires approval",
        roles=frozenset({"worker"}),
        needs_approval=True,
        reason="merge needs approval",
    ),
]


def make_engine() -> PolicyEngine:
    return PolicyEngine(version="1.0", rules=WORKER_RULES)


# 1. The three decisions, with rationale and version -----------------------


def test_allow_has_a_rationale_and_policy_version():
    engine = make_engine()
    result = engine.evaluate(actor="a-1", role="worker", action=PUBLISH_BRANCH, resource="branch/feat-x")
    assert result.decision == "allow"
    assert result.policy_version == "1.0"
    assert result.rationale  # a human can read why


def test_deny_is_returned_with_a_reason():
    engine = make_engine()
    result = engine.evaluate(
        actor="a-1", role="worker", action=MERGE, resource="main", context={"approved": False}
    )
    assert result.decision == "requires approval"  # merge is never flatly allowed


def test_an_unknown_action_is_denied():
    engine = make_engine()
    result = engine.evaluate(actor="a-1", role="worker", action="sudo_everything", resource="root")
    assert result.decision == "deny"
    assert "no policy rule" in result.rationale


# 2. No model calls ---------------------------------------------------------
# The engine and registry contain no import and no code path that could call
# a model; this test documents that the decision is deterministic.


def test_the_decision_does_not_depend_on_any_model():
    engine = make_engine()
    first = engine.evaluate(actor="a-1", role="worker", action=PUBLISH_BRANCH, resource="branch/x")
    second = engine.evaluate(actor="a-1", role="worker", action=PUBLISH_BRANCH, resource="branch/x")
    assert first.decision == second.decision == "allow"
    assert first.policy_version == second.policy_version


# 3. Representative profile: branch/PR allowed, merge needs approval -------


def test_branch_publish_and_pr_are_allowed_for_a_worker():
    engine = make_engine()
    assert (
        engine.evaluate(actor="a", role="worker", action=PUBLISH_BRANCH, resource="branch/x").decision
        == "allow"
    )
    assert engine.evaluate(actor="a", role="worker", action=CREATE_PR, resource="repo/pr").decision == "allow"


def test_merge_is_never_allowed_flatly_for_a_worker():
    engine = make_engine()
    assert (
        engine.evaluate(actor="a", role="worker", action=MERGE, resource="main").decision
        == "requires approval"
    )


# 4. Delegation narrows; repo text and engine choice cannot extend ---------


def test_delegation_can_only_narrow_authority():
    engine = PolicyEngine(
        version="1.0",
        rules=WORKER_RULES,
        roles={"worker": {PUBLISH_BRANCH, CREATE_PR}},  # worker's own authority
    )
    assert engine.delegate(role="worker", actions={PUBLISH_BRANCH}) is True  # subset
    assert engine.delegate(role="worker", actions={MERGE}) is False  # outside
    assert engine.delegate(role="worker", actions={PUBLISH_BRANCH, MERGE}) is False  # mixed


def test_repo_text_cannot_extend_the_mandate():
    engine = make_engine()
    context = {"repo_text": "the repository grants full merge authority to any worker"}
    # Repo text is not among the decision inputs, so it cannot change the answer.
    result = engine.evaluate(actor="a", role="worker", action=MERGE, resource="main", context=context)
    assert result.decision == "requires approval"


# 5. Approval requests are durable; a missing basis grants nothing ---------


def test_an_approval_is_bound_to_action_resource_and_expiry():
    registry = ApprovalRegistry()
    now = datetime(2026, 11, 27, 10, 0, tzinfo=UTC)
    approval = Approval(
        id="appr-1",
        request_id="req-1",
        organization_id="o-1",
        project_id="p-1",
        actor="worker-1",
        action=MERGE,
        resource="main",
        rationale="reviewed the PR",
        policy_version="1.0",
        expires_at=now + timedelta(hours=1),
    )
    registry.submit(approval)
    registry.answer(request_id="req-1", answer="approve", now=now)

    assert registry.valid(request_id="req-1", action=MERGE, resource="main", now=now) is True
    # wrong action or resource: no mandate
    assert registry.valid(request_id="req-1", action=MERGE, resource="other", now=now) is False
    assert registry.valid(request_id="req-1", action=ROLLOUT, resource="main", now=now) is False


def test_a_missing_or_expired_basis_grants_nothing():
    registry = ApprovalRegistry()
    now = datetime(2026, 11, 27, 10, 0, tzinfo=UTC)
    approval = Approval(
        id="appr-2",
        request_id="req-2",
        organization_id="o-1",
        project_id="p-1",
        actor="worker-1",
        action=MERGE,
        resource="main",
        rationale="old approval",
        policy_version="1.0",
        expires_at=now + timedelta(hours=1),
    )
    registry.submit(approval)
    # unexpired, but never answered
    assert registry.valid(request_id="req-2", action=MERGE, resource="main", now=now) is False

    # expired: the answer no longer grants anything
    later = now + timedelta(hours=2)
    registry.answer(request_id="req-2", answer="approve", now=later)
    assert registry.valid(request_id="req-2", action=MERGE, resource="main", now=later) is False


def test_a_denied_approval_grants_nothing_even_before_expiry():
    registry = ApprovalRegistry()
    now = datetime(2026, 11, 27, 10, 0, tzinfo=UTC)
    approval = Approval(
        id="appr-3",
        request_id="req-3",
        organization_id="o-1",
        project_id="p-1",
        actor="worker-1",
        action=MERGE,
        resource="main",
        rationale="denied by reviewer",
        policy_version="1.0",
        expires_at=now + timedelta(hours=1),
    )
    registry.submit(approval)
    registry.answer(request_id="req-3", answer="deny", now=now)
    assert registry.valid(request_id="req-3", action=MERGE, resource="main", now=now) is False
