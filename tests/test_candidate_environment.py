"""The isolated candidate environment, checked against A43.

Issue #36's acceptance criteria, mapped one test each:

1. the candidate runs against a separate test store while the active
   version handles a real issue (A43);
2. the candidate cannot read or change the active queue, reservations,
   worker identity, or external operations;
3. the active version keeps ownership and completes the issue;
4. candidate state, queue, and CI are separate from active operations.

The isolation is structural: the candidate holds its own store and worker
identity, and the only view of the active side is a frozen snapshot of
ready task ids. There is no reference to the active store on the candidate,
so any attempt to read or change active state is refused by construction.
"""

from __future__ import annotations

from dev_org.core import CandidateEnvironment, TaskLifecycle
from dev_org.state.models import Task
from dev_org.state.store import InMemoryStore


def make_task(task_id: str, *, kind: str = "production", priority: str = "P2") -> Task:
    return Task(
        id=task_id,
        organization_id="o-1",
        project_id="p-1",
        title=task_id,
        priority=priority,  # type: ignore[arg-type]
        kind=kind,  # type: ignore[arg-type]
    )


# 1. Separate test store while active work runs (A43) --------------------


def test_the_candidate_runs_against_its_own_store_while_active_work_continues():
    active = InMemoryStore()
    candidate_store = InMemoryStore()
    env = CandidateEnvironment(candidate_store=candidate_store)

    # The active version handles a real issue.
    active_lifecycle = TaskLifecycle(active)
    real_task = make_task("t-real", priority="P0")
    active.save_task(real_task)
    active_lifecycle.dispatch(real_task)
    assert real_task.status == "In progress"

    # The candidate starts against its own store.
    env.start(active_store=active)
    candidate_task = make_task("t-candidate", kind="improvement")
    candidate_store.save_task(candidate_task)
    env.dispatch_candidate(candidate_task)

    # Both sides progressed independently.
    assert env.store is candidate_store
    assert env.store is not active
    assert real_task.status == "In progress"  # active work unaffected


# 2. Cannot read or change the active queue (A43) ------------------------


def test_the_candidate_has_no_reference_to_the_active_store():
    active = InMemoryStore()
    env = CandidateEnvironment(candidate_store=InMemoryStore())
    env.start(active_store=active)

    # The candidate's only view of the active side is a frozen snapshot of
    # ready task ids; it holds no active store reference and no reservation
    # ownership numbers.
    snapshot = env.snapshot()
    assert snapshot is not None
    assert not hasattr(env, "active_store")
    assert not hasattr(env, "active_owner_numbers")
    assert isinstance(snapshot.active_ready_task_ids, tuple)


def test_the_candidate_does_not_see_active_reservation_ownership():
    active = InMemoryStore()
    lifecycle = TaskLifecycle(active)
    task = make_task("t-real", priority="P0")
    active.save_task(task)
    reservation = lifecycle.dispatch(task)

    env = CandidateEnvironment(candidate_store=InMemoryStore())
    snapshot = env.start(active_store=active)

    # The candidate never receives the active owner's number or token.
    assert snapshot.active_ready_task_ids == ()
    assert not hasattr(snapshot, "active_owner_numbers")
    assert not hasattr(snapshot, "active_fencing_token")
    assert reservation.fencing_token  # the active owner still holds it


def test_the_candidate_cannot_change_the_active_queue():
    active = InMemoryStore()
    active_lifecycle = TaskLifecycle(active)
    real_task = make_task("t-real", priority="P0")
    active.save_task(real_task)
    active_lifecycle.dispatch(real_task)

    candidate_store = InMemoryStore()
    env = CandidateEnvironment(candidate_store=candidate_store)
    env.start(active_store=active)

    # The candidate dispatches into its own store; the active task is not
    # touched and the active queue still holds the real issue.
    candidate_task = make_task("t-cand", kind="improvement")
    candidate_store.save_task(candidate_task)
    env.dispatch_candidate(candidate_task)

    active_ready = active.ready_tasks("p-1")
    assert all(t.id != "t-cand" for t in active_ready)
    assert real_task.status == "In progress"


# 3. Active version keeps ownership and completes (A43) ------------------


def test_the_active_version_keeps_ownership_and_completes_the_issue():
    active = InMemoryStore()
    active_lifecycle = TaskLifecycle(active)
    real_task = make_task("t-real", priority="P0")
    active.save_task(real_task)
    reservation = active_lifecycle.dispatch(real_task)

    # The candidate runs against its own store in parallel.
    candidate_store = InMemoryStore()
    env = CandidateEnvironment(candidate_store=candidate_store)
    env.start(active_store=active)
    candidate_task = make_task("t-cand", kind="improvement")
    candidate_store.save_task(candidate_task)

    # The active owner still owns its reservation and completes the issue.
    assert active_lifecycle.can_publish(reservation, ownership_number=reservation.ownership_number) is True
    active_lifecycle.complete(real_task)
    assert real_task.status == "Completed"
    # The candidate's dispatch used its own identity, not the active one.
    candidate_reservation = env.dispatch_candidate(candidate_task)
    assert candidate_reservation.worker_id == env.candidate_worker_id


# 4. Candidate state is separate (A43) -----------------------------------


def test_candidate_state_queue_and_identity_are_separate():
    active = InMemoryStore()
    candidate_store = InMemoryStore()
    env = CandidateEnvironment(candidate_store=candidate_store)

    active.save_task(make_task("t-real", priority="P0"))
    env.start(active_store=active)
    candidate_store.save_task(make_task("t-cand", kind="improvement"))

    # The candidate's next-ready comes from its own store only: the active
    # task is not visible to it.
    candidate_next = env.next_ready("p-1")
    assert candidate_next is not None
    assert candidate_next.id == "t-cand"
    assert candidate_next.id != "t-real"
    # And the candidate worker id is distinct from the active worker's.
    assert env.candidate_worker_id.startswith("candidate-")
