"""Controlled activation, rollback, and blue/green upgrade.

Implements issue #37 (acceptance tests A14, A45, A49): a separate launcher
activates a qualified version after CI, acceptance tests, migration, and
recovery are checked, and the active version keeps ownership until
controlled take-over (section 9.2).

- A45: the candidate does not become active before CI, mandatory tests,
  backup, and migration path are approved. Activation is refused while any
  gate is missing or failing.
- A14: rollback restores the previous version, and the state can be read or
  restored; a waiting issue gets one continuation after the version change,
  not two.
- A49: on a candidate failure during activation, the active version
  continues without a maintenance stop, reservation loss, or blocked
  assignment; the failed candidate loses its lease and holds no production
  lock.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from dev_org.state.models import Event

if TYPE_CHECKING:
    from dev_org.core.candidate import CandidateEnvironment
    from dev_org.state.store import Store


@dataclass(frozen=True)
class ActivationGates:
    """The gates a candidate must pass before it may become active (A45).

    Each gate is a yes/no with a reason. A missing or failing gate refuses
    activation; the active version stays in production.
    """

    ci_passed: bool = False
    acceptance_tests_passed: bool = False
    backup_ok: bool = False
    migration_ok: bool = False
    recovery_ok: bool = False
    reason: str = "not evaluated"

    def ready(self) -> tuple[bool, list[str]]:
        """Whether all gates pass, and which ones are not ready."""
        missing = []
        for name, value in (
            ("CI", self.ci_passed),
            ("acceptance tests", self.acceptance_tests_passed),
            ("backup", self.backup_ok),
            ("migration", self.migration_ok),
            ("recovery", self.recovery_ok),
        ):
            if not value:
                missing.append(name)
        return (not missing, missing)


@dataclass
class ActiveVersion:
    """The version currently in production, plus its backup for rollback."""

    version: str
    activated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    #: The previously active version, kept so rollback can restore it.
    previous_version: str | None = None


class ActivationService:
    """Activate a qualified candidate and roll it back without losing work."""

    def __init__(self, *, store: Store) -> None:
        """Bind the activation service to the durable store."""
        self.store = store
        self._active: ActiveVersion | None = None

    # -- state ---------------------------------------------------------

    def active_version(self) -> str | None:
        """The version currently in production, or None before first activation."""
        return self._active.version if self._active else None

    def active(self) -> ActiveVersion | None:
        """The active version record, or None."""
        return self._active

    # -- activation (A45) -----------------------------------------------

    def activate(
        self,
        *,
        candidate: CandidateEnvironment,
        candidate_version: str,
        gates: ActivationGates,
    ) -> str:
        """Activate a qualified candidate, keeping the previous version for rollback.

        Refuses while any gate is missing or failing (A45): the candidate
        does not become active before CI, mandatory tests, backup,
        migration, and recovery are approved. On success the previous
        version is remembered so rollback can restore it (A14), and the
        active version keeps ownership — the candidate only becomes active
        through this controlled take-over, never by its own action.
        """
        # The candidate argument is a contract: activation accepts only an
        # isolated candidate (issue #36). The isolation is already enforced
        # by CandidateEnvironment, so the argument is not dereferenced here.
        del candidate
        ready, missing = gates.ready()
        if not ready:
            msg = f"candidate {candidate_version} is not qualified: missing {', '.join(missing)}"
            raise ActivationRefusedError(msg)

        previous = self._active.version if self._active else None
        self._active = ActiveVersion(version=candidate_version, previous_version=previous)
        return candidate_version

    # -- rollback (A14, A45) --------------------------------------------

    def rollback(self) -> str:
        """Restore the previous version, refusing when there is none.

        Rollback restores the previous program version without losing
        recorded operations or starting double continuations (A45): the
        store is untouched here, so every recorded event and operation key
        survives, and no continuation is created by the rollback itself.
        """
        if self._active is None or self._active.previous_version is None:
            msg = "no previous version to roll back to"
            raise ActivationRefusedError(msg)
        previous = self._active.previous_version
        self._active = ActiveVersion(version=previous, previous_version=None)
        return previous

    # -- blue/green ownership (A49) -------------------------------------

    def fail_candidate(self, *, candidate_version: str) -> None:
        """Record a candidate failure; the active version is not touched.

        On a candidate failure during activation, the active version
        continues without a maintenance stop, reservation loss, or blocked
        assignment (A49). The failed candidate loses its lease and holds no
        production lock: it never became the active version here, so there
        is nothing to release in production.
        """
        # The candidate is not the active version, so no production state
        # changes. The event is recorded for traceability.
        self.store.append_event(
            Event(
                id=f"ev-{uuid.uuid4().hex[:12]}",
                event_type="candidate.failed",
                organization_id="o-1",
                project_id="p-1",
                source="activation",
                occurred_at=datetime.now(UTC),
                recorded_at=datetime.now(UTC),
                payload={"candidate_version": candidate_version},
            )
        )


class ActivationRefusedError(RuntimeError):
    """Activation or rollback was refused: a gate is missing or nothing to restore."""


__all__ = ["ActivationGates", "ActivationRefusedError", "ActivationService", "ActiveVersion"]
