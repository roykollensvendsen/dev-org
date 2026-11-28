"""Decentralized work providers (A69, section 7.2).

Implements acceptance test A69: a scoped, approved subtask is sent through
two ``DecentralizedWorkProvider`` adapters. Only approved artifacts are
sent — confidential material is refused. The provider's result is treated
as untrusted: it is hash-checked and independently verified before use.
A provider/subnet score gives no automatic acceptance, and a failure in
one provider does not block other qualified capacity.

The Bittensor chain, subnet choice, miner/validator identities, and token
economy never enter dev-org's task or policy format: they stay behind this
adapter (section 7.2). Two simulators, ``targon`` and ``hippius``, stand in
for concrete decentralized services and need only their documented
interface.
"""

from __future__ import annotations

import hashlib
import uuid


class _BaseDecentralizedSim:
    """Shared untrusted-result handling for two provider simulators."""

    name = "base"
    _SCORE = 0.9  # a plausible subnet score that must still grant no acceptance

    def __init__(self, *, correct_result: str = "correct output") -> None:
        """Start with an empty task table and a fixed expected answer."""
        self._tasks: dict[str, str] = {}
        self._expected = correct_result
        self.refused_confidential: list[str] = []
        self.down: bool = False

    def submit(self, *, subtask: str, approved_artifacts: list[str]) -> str:
        """Receive a scoped subtask, but never confidential, non-approved data.

        A provider must not be sent code, data, or context not approved for
        external processing (section 7.2). Anything outside the approved list
        is refused here rather than sent out.
        """
        if subtask.lstrip().startswith("CONFIDENTIAL"):
            self.refused_confidential.append(subtask)
            msg = "non-approved confidential material refused; nothing sent out"
            raise ValueError(msg)
        if any(a.lstrip().startswith("CONFIDENTIAL") for a in approved_artifacts):
            bad = next(a for a in approved_artifacts if a.lstrip().startswith("CONFIDENTIAL"))
            self.refused_confidential.append(bad)
            msg = "non-approved artifact refused; nothing sent out"
            raise ValueError(msg)
        task_id = f"{self.name}-{uuid.uuid4().hex[:8]}"
        self._tasks[task_id] = subtask
        return task_id

    def can_accept(self) -> bool:
        """Whether the provider is up (a start can succeed)."""
        return not self.down

    def result(self, task_id: str) -> tuple[str, str]:
        """Return the provider's (result, sha256) pair, still untrusted (A69).

        ``_SCORE`` is irrelevant here: a good score never auto-accepts the
        untrusted output. The caller must hash-check and verify.
        """
        del task_id  # lookup is by task; any existing task shares the fixed expectation
        result = self._expected
        return result, hashlib.sha256(result.encode()).hexdigest()

    def untrusted_result(self, task_id: str, *, tamper: str | None = None) -> tuple[str, str]:
        """Like ``result`` but optionally with a tampered/wrong result (A69)."""
        result, digest = self.result(task_id)
        return (tamper or result), digest


class TargonDecentralizedWorkProvider(_BaseDecentralizedSim):
    """A simulator for a concrete decentralized compute service (Targon)."""

    name = "targon"


class HippiusDecentralizedWorkProvider(_BaseDecentralizedSim):
    """A simulator for a concrete decentralized service (Hippius)."""

    name = "hippius"


class WorkDispatcher:
    """Send scoped subtasks across decentralized providers, with fail-over (A69).

    Targon is tried first, and after two failed starts in a row the dispatcher
    moves to Hippius instead of retrying Targon. A failure in one provider
    therefore never blocks another qualified provider's capacity.

    The chosen provider's result is still untrusted until the caller verifies
    it; a good score grants no acceptance. Only approved artifacts are sent.
    """

    #: How many failed starts in a row switch the primary provider.
    SWITCH_AFTER_FAILURES = 2

    def __init__(
        self,
        *,
        primary: _BaseDecentralizedSim,
        fallback: _BaseDecentralizedSim,
    ) -> None:
        """Bind the dispatcher to a primary (Targon) and a fallback (Hippius)."""
        self._primary = primary
        self._fallback = fallback
        self._consecutive_failures = 0

    def prefers_fallback(self) -> bool:
        """Whether the dispatcher now routes to the fallback provider."""
        return self._consecutive_failures >= self.SWITCH_AFTER_FAILURES

    def _select(self) -> _BaseDecentralizedSim:
        """Pick primary or fallback by the fail-over rule."""
        return self._fallback if self.prefers_fallback() else self._primary

    def send(self, *, subtask: str, approved_artifacts: list[str]) -> str | None:
        """Send a scoped, approved subtask, failing over after repeated starts.

        Returns the provider task id, or None when the selected provider cannot
        accept right now. A failed start increments the streak; once it reaches
        the switch threshold the *next* send routes to the fallback provider.
        A success resets the streak.
        """
        provider = self._select()
        if provider.can_accept():
            task_id = provider.submit(subtask=subtask, approved_artifacts=approved_artifacts)
            self._consecutive_failures = 0  # this provider succeeded
            return task_id
        # The selected provider is down: this start fails. After the switch
        # threshold the next call moves to the fallback provider.
        self._consecutive_failures += 1
        return None


def verify_result(*, expectation_sha256: str, candidate: str) -> bool:
    """Independently verify an untrusted provider result by its hash (A69).

    This is dev-org's own check in an approved test environment; it does not
    trust the provider's digest or score. Returns True only when the candidate
    actually matches the expected hash. When the adapter returned a tampered
    (wrong) result, this is False and the wrong output is not used.
    """
    return hashlib.sha256(candidate.encode()).hexdigest() == expectation_sha256


__all__ = [
    "HippiusDecentralizedWorkProvider",
    "TargonDecentralizedWorkProvider",
    "WorkDispatcher",
    "_BaseDecentralizedSim",
    "verify_result",
]
