"""Policy evaluation: allow, deny, or requires approval, without model calls.

The policy module (specification 3.2) evaluates a concrete action and
resource against identity, mandate, and conditions, and returns a decision
with a rationale and a policy version. It never calls a model. The same
evaluator is used by the performing call and by the advance assessment.

This module is the decision module only; the gateway's external enforcement
is a separate issue. Rules are versioned and immutable once loaded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datetime import datetime

    from dev_org.state.models import Approval

Decision = Literal["allow", "deny", "requires approval"]

#: Action names the policy can decide on, from section 3.2 and 10.3.
PUBLISH_BRANCH = "publish_branch"
CREATE_PR = "create_pr"
ORDER_CI = "order_ci"
MERGE = "merge"
ROLLOUT = "rollout"
CHANGE_WORKSPACE = "change_workspace"


@dataclass(frozen=True)
class Rule:
    """One versioned rule: what an action needs, and what it is granted."""

    action: str
    decision: Decision
    #: Roles that may perform the action; an empty set means any role.
    roles: frozenset[str] = frozenset()
    #: Named conditions in the evaluation context that must be present and
    #: truthy. A missing necessary basis must not grant permission.
    requires: frozenset[str] = frozenset()
    #: When true, the action needs a recorded, unexpired approval.
    needs_approval: bool = False
    #: Why this rule exists; shown in the rationale.
    reason: str = ""


@dataclass
class Evaluation:
    """The outcome of one evaluation."""

    decision: Decision
    rationale: str
    policy_version: str
    #: Conditions the decision rests on, for the advance assessment.
    conditions: dict[str, object] = field(default_factory=dict)


class PolicyEngine:
    """Evaluate actions against an immutable, versioned rule set."""

    def __init__(self, *, version: str, rules: list[Rule], roles: dict[str, set[str]] | None = None) -> None:
        """Bind the engine to a policy version, rule set, and role map."""
        self.version = version
        self.rules = {rule.action: rule for rule in rules}
        #: role -> set of actions the role is allowed to attempt; used to
        #: narrow, never to extend. Absent means "decide by rule only".
        self.roles = roles or {}

    def evaluate(
        self,
        *,
        actor: str,
        role: str,
        action: str,
        resource: str,
        context: dict[str, object] | None = None,
    ) -> Evaluation:
        """Decide one action. Never calls a model; never performs the action."""
        del actor  # identity is carried by role + context; kept for the contract
        context = context or {}
        rule = self.rules.get(action)
        if rule is None:
            return Evaluation("deny", f"no policy rule for action {action}", self.version)

        if rule.roles and role not in rule.roles:
            return Evaluation(
                "deny",
                f"role {role} is not allowed to {action}",
                self.version,
            )

        missing = [name for name in rule.requires if not context.get(name)]
        if missing:
            return Evaluation(
                "deny",
                f"missing necessary basis: {', '.join(sorted(missing))}",
                self.version,
            )

        if rule.needs_approval:
            return Evaluation(
                "requires approval",
                f"{rule.reason or action} needs a recorded, unexpired approval",
                self.version,
                {"approval_required": True, "resource": resource},
            )

        return Evaluation(
            rule.decision,
            rule.reason or f"rule for {action}",
            self.version,
            {"role": role, "resource": resource},
        )

    def delegate(self, *, role: str, actions: set[str], context: dict[str, object] | None = None) -> bool:
        """Return whether a delegation is within the role's authority.

        Delegation can only narrow authority (section 3.2): the delegated
        actions must be a subset of what the role already has. Repo text and
        engine choice are not among the inputs, so they cannot extend it.
        """
        del context  # no contextual input may widen a delegation
        allowed = self.roles.get(role)
        if allowed is None:
            return True  # no role map: nothing to narrow against
        return actions <= allowed


class ApprovalRegistry:
    """Record approval requests and answers durably, and judge validity.

    Section 3.2: an approval request is concrete and scoped to action,
    resource, and validity; the answer is recorded durably; a missing or
    expired basis grants nothing.
    """

    def __init__(self) -> None:
        """Create an empty registry."""
        self._by_request: dict[str, Approval] = {}

    def submit(self, approval: Approval) -> None:
        """Record a new approval request."""
        self._by_request[approval.request_id] = approval

    def get(self, request_id: str) -> Approval | None:
        """Return the recorded approval for a request ID, or None."""
        return self._by_request.get(request_id)

    def answer(self, *, request_id: str, answer: str, now: datetime) -> None:
        """Record a durable answer; expired requests cannot be answered."""
        approval = self._by_request.get(request_id)
        if approval is None:
            raise KeyError(request_id)
        if now >= approval.expires_at:
            approval.status = "expired"
            approval.answered_at = now
            approval.answer = "expired"
            return
        approval.status = "approved" if answer == "approve" else "denied"
        approval.answered_at = now
        approval.answer = answer

    def valid(self, *, request_id: str, action: str, resource: str, now: datetime) -> bool:
        """A valid approval matches action and resource, is approved, and is unexpired."""
        approval = self._by_request.get(request_id)
        if approval is None or approval.status != "approved":
            return False
        if approval.action != action or approval.resource != resource:
            return False
        return now < approval.expires_at
