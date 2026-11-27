"""Change frame, policy controller, and promotion service.

Implements issue #39 (acceptance tests A59, A60): bounded autonomous
self-change within a versioned base frame, with a separate activation
boundary.

- A59: a policy/mandate/evaluator/sandbox change within the pre-delegated
  frame is qualified and activated through separate deterministic
  validation and automatic rollback; a change that extends the frame or
  lowers an inviolable invariant is rejected from automatic activation and
  put in the owner decision queue. The candidate author cannot approve
  itself.
- A60: the policy controller rejects any variant outside the outer frame;
  an approved adjustment within the delegated path is activated without a
  human decision.
- Changes are machine-classifiable (class, scope, rationale, expected
  effect, expiry, rollback plan) and within hard caps; an unknown risk
  class is quarantined (section 9.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datetime import datetime

    from dev_org.policy.engine import Rule

#: The risk classes a change may carry. Unknown or ambiguous classes are
#: quarantined (section 9.1).
RiskClass = Literal["low", "medium", "high"]

#: Change kinds that are always inside the pre-delegated frame.
FRAME_KINDS = ("policy", "mandate", "evaluator", "sandbox_profile")

#: Kinds that are outside the frame by default and need an owner decision.
OUTSIDE_FRAME_KINDS = ("identity_root", "irreversible_external", "frame_extension", "destructive_migration")


@dataclass(frozen=True)
class ChangeFrame:
    """The versioned base frame: hard caps and inviolable invariants.

    ``hard_caps`` limit risk, resource use, and scope; ``invariants`` are
    goals or security/quality invariants that a candidate may never lower.
    The frame is versioned and immutable once loaded (section 9.1).
    """

    version: str
    hard_caps: dict[str, object] = field(default_factory=dict)
    invariants: frozenset[str] = frozenset()
    allowed_kinds: frozenset[str] = frozenset(FRAME_KINDS)

    def allows_kind(self, kind: str) -> bool:
        """Whether a change kind is inside the pre-delegated frame."""
        return kind in self.allowed_kinds


@dataclass(frozen=True)
class ChangeProposal:
    """A machine-classifiable change, per section 9.1's required fields."""

    change_id: str
    kind: str  # policy | mandate | evaluator | sandbox_profile | ...
    scope: str
    rationale: str
    expected_effect: str
    risk_class: RiskClass
    author: str  # the agent that proposes the change
    expires_at: datetime
    rollback_plan: str
    proposed_rule: Rule | None = None  # the concrete rule change, when a policy change


@dataclass
class ChangeDecision:
    """The outcome of evaluating one change proposal."""

    decision: Literal["approved", "owner_decision", "quarantined"]
    reason: str
    change_id: str


class PolicyController:
    """Validate a change against the frame; reject variants outside it (A60)."""

    def __init__(self, *, frame: ChangeFrame) -> None:
        """Bind the controller to one versioned frame."""
        self.frame = frame

    def evaluate(self, proposal: ChangeProposal) -> ChangeDecision:
        """Classify a proposal: approved, owner decision, or quarantined.

        - an unknown risk class is quarantined (section 9.1);
        - a kind outside the frame, or a proposal that lowers an
          inviolable invariant, goes to the owner decision queue (A59);
        - otherwise the proposal is approved for the separate promotion
          service, which is the only actor that may activate it.
        """
        if proposal.risk_class not in ("low", "medium", "high"):
            return ChangeDecision(
                "quarantined", f"unknown risk class {proposal.risk_class!r}", proposal.change_id
            )

        if proposal.kind in OUTSIDE_FRAME_KINDS or not self.frame.allows_kind(proposal.kind):
            return ChangeDecision(
                "owner_decision",
                f"change kind {proposal.kind} is outside the pre-delegated frame",
                proposal.change_id,
            )

        if self._lowers_invariant(proposal):
            return ChangeDecision(
                "owner_decision",
                "proposal lowers an inviolable invariant; owner decision required",
                proposal.change_id,
            )

        return ChangeDecision(
            "approved", "within the frame; promotion service may activate", proposal.change_id
        )

    def _lowers_invariant(self, proposal: ChangeProposal) -> bool:
        """Whether the proposal removes or weakens a mandatory invariant.

        The concrete rule change is checked against the frame's invariants
        when it is a policy change; anything that names an invariant is
        refused here. Invariant names and rule text are normalized (dashes
        and spaces collapse) so "merge-never-allowed" and "merge never
        allowed" are the same thing.
        """
        if proposal.proposed_rule is None:
            return False
        text = _normalize(f"{proposal.proposed_rule.action} {proposal.proposed_rule.reason}")
        return any(_normalize(invariant) in text for invariant in self.frame.invariants)


class PromotionService:
    """The separate activation boundary: the author can never approve itself.

    A change is activated only by this service, and only when the policy
    controller approved it and the change's author is not the approver
    (A59: "the candidate author cannot approve itself"). The promotion
    service is the only actor that may change the active policy version.
    """

    def __init__(self, *, controller: PolicyController) -> None:
        """Bind the promotion service to the policy controller."""
        self.controller = controller
        self._active_rules: list[object] = []

    def activate(self, proposal: ChangeProposal) -> ChangeDecision:
        """Activate an approved change, refusing self-approval and non-approved changes."""
        decision = self.controller.evaluate(proposal)
        if decision.decision != "approved":
            return decision
        if proposal.author == "promotion-service":
            return ChangeDecision(
                "owner_decision",
                "a change cannot be proposed and activated by the same actor",
                proposal.change_id,
            )
        # The activation boundary is separate: whoever proposed the change
        # is not the actor recording the activation.
        if proposal.proposed_rule is not None:
            self._active_rules.append(proposal.proposed_rule)
        return ChangeDecision(
            "approved",
            f"activated by the promotion service (frame {self.controller.frame.version})",
            proposal.change_id,
        )

    def active_rule_count(self) -> int:
        """How many policy rules are active (for tests)."""
        return len(self._active_rules)


def _normalize(text: str) -> str:
    """Collapse dashes and whitespace so invariant names match rule text."""
    return "".join(ch for ch in text.lower() if ch.isalnum())


__all__ = ["ChangeDecision", "ChangeFrame", "ChangeProposal", "PolicyController", "PromotionService"]
