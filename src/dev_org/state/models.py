"""Durable state: the domain objects the organization's work is built on.

The first data model is fixed by the specification (section 10.1): every
object has an internal stable ID, `Task` points to external board IDs, and
`Attempt` points to the engine's session ID as a nullable runtime
reference. An event and a state change are written in the same database
transaction.

These are the contracts issue #4 documents. They are Pydantic models so the
chosen MVP baseline (Python 3.14, Pydantic 2.x) validates them on load, and
so a later PostgreSQL adapter can persist them without redefining them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

UTCNOW = lambda: datetime.now(UTC)  # noqa: E731 - a callable default


class DomainModel(BaseModel):
    """Base for every durable object: a stable internal ID."""

    id: str = Field(min_length=1, description="stable internal ID, never reused")


class Task(DomainModel):
    """A piece of work, tied to external board IDs."""

    organization_id: str
    project_id: str
    external_id: str | None = None  # the board's own ID, when there is one
    title: str
    priority: Literal["P0", "P1", "P2"] = "P2"
    status: str = "Ready"
    acceptance_criteria: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=UTCNOW)
    updated_at: datetime = Field(default_factory=UTCNOW)


class Attempt(DomainModel):
    """One run of a task: can succeed, fail, or be interrupted."""

    task_id: str
    engine_session_id: str | None = None  # the engine's conversation/session ID
    status: Literal["running", "waiting", "completed", "failed", "interrupted"] = "running"
    started_at: datetime = Field(default_factory=UTCNOW)
    ended_at: datetime | None = None


class Reservation(DomainModel):
    """Time-limited ownership of an attempt, with a fencing token."""

    attempt_id: str
    worker_id: str
    ownership_number: int
    fencing_token: str
    lease_expires_at: datetime
    created_at: datetime = Field(default_factory=UTCNOW)


class Checkpoint(DomainModel):
    """An engine-independent snapshot a different engine can continue from."""

    attempt_id: str
    task_id: str
    code_reference: str | None = None  # branch/commit/archive reference
    test_evidence: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    wait_conditions: list[str] = Field(default_factory=list)
    next_action: str | None = None
    created_at: datetime = Field(default_factory=UTCNOW)


class Event(DomainModel):
    """An append-only, versioned record of what happened.

    The schema is `dev-org.event.v1` as fixed by the specification (section
    10.1). Time is UTC ISO 8601. An unknown schema version or an invalid
    critical event is quarantined and cannot change authoritative state.
    """

    schema_version: Literal["dev-org.event.v1"] = "dev-org.event.v1"
    event_type: str
    organization_id: str
    project_id: str
    task_id: str | None = None
    attempt_id: str | None = None
    source: str
    source_sequence: int | None = None
    occurred_at: datetime = Field(default_factory=UTCNOW)
    recorded_at: datetime = Field(default_factory=UTCNOW)
    causation_id: str | None = None
    idempotency_key: str | None = None  # for side effects
    payload: dict[str, Any] = Field(default_factory=dict)
