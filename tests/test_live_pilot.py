"""Live pilot, read-only: a real GitHub issue flows through dev-org's core.

This is the "live parts, no PR" half of the first pilot (docs/pilot.md): it
swaps the deterministic board double for the real, authenticated GitHub
read, and runs the core (task lifecycle, change frame, policy) over a real
issue from this repository. It opens no PR, makes no external write, and
calls no model, so it is safe to run on any machine that has `gh`
authenticated and network access.

Marked ``live`` and skipped without GitHub auth, so the default CI suite in
a fresh checkout does not depend on a network or a token. Run it with:

    uv run python -m pytest tests/test_live_pilot.py -m live -q

The default issue (63) and each repo's real open history exercise the same
path. The assertion is deliberately structural: the issue was fetched for
real, dispatched, and judged — not that any particular plan is correct.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime

import pytest

from dev_org.core.change_frame import ChangeFrame, ChangeProposal, PolicyController, PromotionService
from dev_org.core.lifecycle import IN_PROGRESS, TaskLifecycle
from dev_org.state.models import Task
from dev_org.state.store import InMemoryStore

REPO = "roykollensvendsen/dev-org"
#: A real issue from this repo, closed when the range it tracked was merged.
ISSUE = 63


def _gh_authed() -> bool:
    """Whether an authenticated gh client is reachable right now."""
    probe = subprocess.run(
        ["gh", "auth", "status", "-h", "github.com"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,  # returncode carries the auth status; a non-zero is expected when not authed
    )
    return probe.returncode == 0


pytestmark = pytest.mark.skipif(not _gh_authed(), reason="gh is not installed or not authenticated")


def _fetch_issue(repo: str, number: int) -> dict[str, str]:
    """Read one real issue over GitHub; fails loudly without auth or network."""
    probe = subprocess.run(
        ["gh", "issue", "view", str(number), "-R", repo, "--json", "title,labels"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    data = json.loads(probe.stdout)
    labels = [label["name"] for label in data.get("labels", [])]
    priority = "P0" if any(label == "priority:p0" for label in labels) else "P2"
    return {"external_id": f"GH-{number}", "title": data["title"], "priority": priority}


@pytest.mark.live
def test_a_real_issue_is_dispatched_and_judged_by_the_live_core() -> None:
    """A real GitHub issue moves through the lifecycle and a change proposal is approved."""
    store = InMemoryStore()
    clock = lambda: datetime.now(UTC)  # noqa: E731 - a live probe needs real time
    lifecycle = TaskLifecycle(store, clock)

    issue = _fetch_issue(REPO, ISSUE)
    task = Task(
        id=f"t-{ISSUE}",
        organization_id="o-1",
        project_id="p-1",
        external_id=issue["external_id"],
        title=issue["title"],
        priority=issue["priority"],  # type: ignore[arg-type]
    )
    store.save_task(task)
    lifecycle.dispatch(task)

    # The core really dispatched a real issue, and its change frame judges a
    # proposal over that issue's scope as within the pre-delegated frame.
    assert task.status == IN_PROGRESS
    proposal = ChangeProposal(
        change_id=f"chg-{ISSUE}",
        kind="evaluator",
        scope=issue["title"],
        rationale="live pilot: a real issue through the core",
        expected_effect="a valid proposal resolves",
        risk_class="low",
        author="pilot",
        expires_at=datetime.now(UTC),
        rollback_plan="no-op pilot",
    )
    controller = PolicyController(frame=ChangeFrame(version="1.0"))
    decision = controller.evaluate(proposal)
    promotion = PromotionService(controller=controller).activate(proposal)
    assert decision.decision == "approved"
    assert promotion.decision == "approved"

    # One lifecycle transition was recorded against the issue's task id.
    assert any(e.event_type == "task.dispatched" and e.task_id == task.id for e in store.events)
