"""Policy module: evaluates versioned rules without model calls.

The policy module (section 3.2) evaluates a concrete action and resource
against identity, mandate, and conditions, and returns allow, deny, or
requires approval with a rationale and policy version. It never calls a
model; the same evaluator is used by the performing call and by
`evaluate_action`.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

Decision = Literal["allow", "deny", "requires approval"]


@runtime_checkable
class PolicyEvaluator(Protocol):
    """Evaluate one action against the current policy."""

    def evaluate(
        self, *, actor: str, action: str, resource: str, context: dict[str, object]
    ) -> tuple[Decision, str, str]:
        """Return (decision, rationale, policy version)."""
        ...


__all__ = ["Decision", "PolicyEvaluator"]
