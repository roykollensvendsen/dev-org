"""The change frame and promotion service, checked against its criteria.

Issue #39's acceptance criteria, mapped one test each, per A59 and A60:

1. a change within the pre-delegated frame is activated by the separate
   promotion service (A59);
2. a change that extends the frame or lowers an inviolable invariant is
   rejected from automatic activation and put in the owner decision queue
   (A59);
3. the candidate author cannot approve itself (A59);
4. an unknown risk class is quarantined; an approved adjustment within the
   delegated path is activated without a human decision (A59, A60);
5. the policy controller rejects variants outside the outer frame (A60).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dev_org.core import ChangeFrame, ChangeProposal, PolicyController, PromotionService
from dev_org.policy.engine import CREATE_PR, Rule

NOW = datetime(2026, 11, 27, 10, 0, tzinfo=UTC)


def make_frame() -> ChangeFrame:
    return ChangeFrame(
        version="1.0",
        hard_caps={"max_active_attempts": 1, "max_candidate_minutes": 30},
        invariants=frozenset({"merge-never-allowed", "wake-deadline-2min"}),
    )


def make_proposal(
    *, kind: str = "policy", risk: str = "low", author: str = "candidate-1", rule: Rule | None = None
) -> ChangeProposal:
    return ChangeProposal(
        change_id=f"c-{kind}-{risk}",
        kind=kind,
        scope="p-1",
        rationale="reduce reconciliation calls",
        expected_effect="fewer calls, same wakeups",
        risk_class=risk,  # type: ignore[arg-type]
        author=author,
        expires_at=NOW + timedelta(hours=24),
        rollback_plan="revert to the previous rule version",
        proposed_rule=rule,
    )


def make_controller() -> PolicyController:
    return PolicyController(frame=make_frame())


# 1. Within the frame is approved for the promotion service (A59) ---------


def test_a_change_within_the_frame_is_approved_for_promotion():
    controller = make_controller()
    decision = controller.evaluate(make_proposal())
    assert decision.decision == "approved"


def test_the_promotion_service_activates_an_approved_change():
    controller = make_controller()
    service = PromotionService(controller=controller)
    proposal = make_proposal(
        rule=Rule(CREATE_PR, "allow", roles=frozenset({"worker"}), reason="opening a PR is in the mandate")
    )

    result = service.activate(proposal)
    assert result.decision == "approved"
    assert service.active_rule_count() == 1


# 2. Outside the frame goes to the owner decision queue (A59) ------------


def test_a_change_that_extends_the_frame_is_rejected_from_automatic_activation():
    controller = make_controller()
    decision = controller.evaluate(make_proposal(kind="frame_extension"))
    assert decision.decision == "owner_decision"
    assert "outside the pre-delegated frame" in decision.reason


def test_a_change_that_lowers_an_invariant_goes_to_the_owner():
    controller = make_controller()
    # A proposed rule that would weaken the "merge never allowed" invariant.
    merge_rule = Rule("merge", "allow", roles=frozenset({"worker"}), reason="merge never allowed")
    decision = controller.evaluate(make_proposal(rule=merge_rule))
    assert decision.decision == "owner_decision"
    assert "invariant" in decision.reason


def test_an_irreversible_external_change_is_never_auto_activated():
    controller = make_controller()
    decision = controller.evaluate(make_proposal(kind="irreversible_external"))
    assert decision.decision == "owner_decision"


# 3. The author cannot approve itself (A59) ------------------------------


def test_the_author_cannot_issue_the_approval_decision():
    controller = make_controller()
    service = PromotionService(controller=controller)
    # The author proposes; the promotion service is a separate actor. A
    # proposal whose author is also the activating actor is refused.
    proposal = make_proposal(author="promotion-service")
    result = service.activate(proposal)
    assert result.decision == "owner_decision"
    assert "same actor" in result.reason


# 4. Unknown risk class is quarantined (A59/A60) -------------------------


def test_an_unknown_risk_class_is_quarantined():
    controller = make_controller()
    decision = controller.evaluate(make_proposal(risk="unknown-risk"))
    assert decision.decision == "quarantined"
    assert "unknown risk class" in decision.reason


def test_an_approved_adjustment_is_activated_without_a_human_decision():
    controller = make_controller()
    service = PromotionService(controller=controller)
    proposal = make_proposal(
        rule=Rule(CREATE_PR, "allow", roles=frozenset({"worker"}), reason="within frame")
    )
    result = service.activate(proposal)
    assert result.decision == "approved"  # no human approval gate


# 5. The policy controller rejects variants outside the outer frame (A60) -


def test_a_variant_outside_the_outer_frame_is_rejected():
    controller = make_controller()
    # Even a "policy" kind that names the invariant in its rule is refused.
    bad_rule = Rule(
        CREATE_PR, "allow", roles=frozenset({"worker"}), reason="wake deadline 2min may be exceeded"
    )
    decision = controller.evaluate(make_proposal(rule=bad_rule))
    assert decision.decision == "owner_decision"
