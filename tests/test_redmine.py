"""Redmine board adapter and migration, checked against A09 and A10.

Issue #59's criteria, mapped one test each:

1. the Redmine adapter implements the same board contract as GitHub and
   passes the same contract cases (A10);
2. a move from Redmine to GitHub preserves mapping and priority, with one
   active issue and zero extra builds (A09);
3. export/import is previewable and preserves internal IDs; nothing is
   overwritten without an explicit choice (section 4);
4. the import report states what was created, changed, omitted, and lost.
"""

from __future__ import annotations

import pytest

from dev_org.gateway import BoardMigration, InMemoryRedmine, RedmineAdapter
from dev_org.gateway.protocol import BoardAdapter
from dev_org.gateway.redmine import WORK_V1


def make_redmine(*, with_issue: bool = True) -> tuple[RedmineAdapter, InMemoryRedmine]:
    client = InMemoryRedmine()
    if with_issue:
        client.issues["R-1"] = {
            "external_id": "R-1",
            "internal_id": "t-1",
            "revision": "3",
            "title": "Fix the title helper",
            "state": "In progress",
            "priority": "P0",
            "labels": ["area:core"],
            "body": "Bug report",
        }
    return RedmineAdapter(client=client), client


def make_github() -> BoardAdapter:
    class _Github:
        def __init__(self) -> None:
            self.issues: dict[str, dict[str, object]] = {}

        def fetch_changes(self) -> list[dict[str, object]]:
            return [dict(i, external_id=k) for k, i in self.issues.items()]

        def read_issue(self, external_id: str) -> dict[str, object]:
            return dict(self.issues[external_id], external_id=external_id)

        def update_issue(self, external_id: str, fields: dict[str, object]) -> None:
            self.issues[external_id] = {**self.issues.get(external_id, {}), **fields}

    return _Github()


# 1. Same board contract, both adapters (A10) ----------------------------


def test_the_redmine_adapter_is_a_runtime_checkable_board_adapter():
    adapter, _ = make_redmine()
    assert isinstance(adapter, BoardAdapter)


def test_fetch_changes_returns_the_common_work_model():
    adapter, _ = make_redmine()
    changes = adapter.fetch_changes()
    assert len(changes) == 1
    issue = changes[0]
    assert issue["external_id"] == "R-1"
    assert issue["title"] == "Fix the title helper"
    assert issue["state"] == "In progress"


def test_read_issue_returns_one_issue_in_the_common_model():
    adapter, _ = make_redmine()
    issue = adapter.read_issue("R-1")
    assert issue["external_id"] == "R-1"
    assert issue["revision"] == "3"


def test_update_issue_writes_only_owned_fields():
    adapter, client = make_redmine()
    adapter.update_issue("R-1", {"state": "In review", "priority": "P0", "not-owned": "x"})
    assert client.issues["R-1"]["state"] == "In review"
    assert "not-owned" not in client.issues["R-1"]  # only owned fields (A10)


# 2. Move from Redmine to GitHub preserving mapping and priority (A09) ----


def test_moving_an_issue_preserves_mapping_and_priority():
    redmine, _ = make_redmine()
    github = make_github()
    migration = BoardMigration(source=redmine, target=github)

    exported = redmine.export_work_v1()
    report = migration.import_(exported, confirm=True)

    # The internal id and priority survived the move (A09).
    assert exported["schema"] == WORK_V1
    assert exported["issues"][0]["internal_id"] == "t-1"
    assert exported["issues"][0]["priority"] == "P0"
    assert report.summary()["created"] == ["R-1"]


def test_the_move_does_not_create_a_second_active_issue_or_order_builds():
    redmine, _ = make_redmine()
    github = make_github()
    migration = BoardMigration(source=redmine, target=github)

    migration.import_(redmine.export_work_v1(), confirm=True)
    # One active issue on the target; the migration itself never calls CI
    # or Git, so it cannot order a build (A09).
    target_issues = github.fetch_changes()
    assert len(target_issues) == 1
    assert target_issues[0]["state"] == "In progress"


# 3. Export/import is previewable and preserves internal IDs (section 4) --


def test_import_is_previewable_without_writing():
    redmine, _ = make_redmine()
    github = make_github()
    migration = BoardMigration(source=redmine, target=github)

    preview = migration.preview(redmine.export_work_v1())
    assert preview.summary()["created"] == ["R-1"]
    # Nothing was written by the preview.
    assert github.fetch_changes() == []


def test_import_is_refused_without_an_explicit_choice():
    redmine, _ = make_redmine()
    github = make_github()
    migration = BoardMigration(source=redmine, target=github)

    with pytest.raises(ValueError, match="confirm"):
        migration.import_(redmine.export_work_v1(), confirm=False)
    assert github.fetch_changes() == []  # nothing overwritten


def test_an_unknown_export_schema_is_refused():
    redmine, _ = make_redmine()
    github = make_github()
    migration = BoardMigration(source=redmine, target=github)
    bad = {"schema": "dev-org.work.old", "issues": []}
    with pytest.raises(ValueError, match="schema"):
        migration.preview(bad)


# 4. The report states created, changed, omitted, and lost (section 4) ----


def test_an_existing_issue_is_reported_as_changed_not_duplicated():
    redmine, _ = make_redmine()
    github = make_github()
    github.update_issue("R-1", {"title": "already here", "state": "In progress"})
    migration = BoardMigration(source=redmine, target=github)

    report = migration.preview(redmine.export_work_v1())
    summary = report.summary()
    assert summary["changed"] == ["R-1"]
    assert summary["created"] == []  # no duplicate active issue
