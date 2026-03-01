"""Tests for github_monitor.store."""

from __future__ import annotations

from datetime import UTC, datetime

from github_monitor.poller import PullRequest
from github_monitor.store import PRStore, StateDiff, StoreStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pr(
    number: int = 1,
    repo: str = "owner/repo",
    title: str = "Fix bug",
    updated_at: str = "2025-06-15T10:00:00Z",
) -> PullRequest:
    """Build a PullRequest for testing."""
    return PullRequest(
        url=f"https://github.com/{repo}/pull/{number}",
        api_url=f"https://api.github.com/repos/{repo}/pulls/{number}",
        title=title,
        repo_full_name=repo,
        author="alice",
        author_avatar_url=f"https://avatars.githubusercontent.com/u/{number}",
        number=number,
        updated_at=datetime.fromisoformat(updated_at),
        review_requested=True,
        assigned=False,
    )


# ---------------------------------------------------------------------------
# StateDiff
# ---------------------------------------------------------------------------


class TestStateDiff:
    def test_default_empty_lists(self) -> None:
        diff = StateDiff()
        assert diff.new_prs == []
        assert diff.closed_prs == []
        assert diff.updated_prs == []

    def test_has_changes_false_when_empty(self) -> None:
        diff = StateDiff()
        assert diff.has_changes is False

    def test_has_changes_true_with_new_prs(self) -> None:
        diff = StateDiff(new_prs=[_make_pr()])
        assert diff.has_changes is True

    def test_has_changes_true_with_closed_prs(self) -> None:
        diff = StateDiff(closed_prs=[_make_pr()])
        assert diff.has_changes is True

    def test_has_changes_true_with_updated_prs(self) -> None:
        diff = StateDiff(updated_prs=[_make_pr()])
        assert diff.has_changes is True

    def test_frozen(self) -> None:
        diff = StateDiff()
        try:
            diff.new_prs = []  # type: ignore[misc]
        except AttributeError:
            pass
        else:
            msg = "StateDiff should be frozen"
            raise AssertionError(msg)


# ---------------------------------------------------------------------------
# StoreStatus
# ---------------------------------------------------------------------------


class TestStoreStatus:
    def test_fields(self) -> None:
        now = datetime.now(tz=UTC)
        status = StoreStatus(pr_count=5, last_updated=now)
        assert status.pr_count == 5
        assert status.last_updated == now

    def test_frozen(self) -> None:
        status = StoreStatus(pr_count=0, last_updated=None)
        try:
            status.pr_count = 1  # type: ignore[misc]
        except AttributeError:
            pass
        else:
            msg = "StoreStatus should be frozen"
            raise AssertionError(msg)


# ---------------------------------------------------------------------------
# PRStore — first poll
# ---------------------------------------------------------------------------


class TestFirstPoll:
    def test_all_prs_are_new(self) -> None:
        store = PRStore()
        prs = [_make_pr(number=1), _make_pr(number=2)]
        diff = store.update(prs)

        assert len(diff.new_prs) == 2
        assert diff.closed_prs == []
        assert diff.updated_prs == []

    def test_empty_first_poll(self) -> None:
        store = PRStore()
        diff = store.update([])

        assert diff.new_prs == []
        assert diff.closed_prs == []
        assert diff.updated_prs == []
        assert diff.has_changes is False


# ---------------------------------------------------------------------------
# PRStore — no changes
# ---------------------------------------------------------------------------


class TestNoDiff:
    def test_same_prs_twice_produces_empty_diff(self) -> None:
        store = PRStore()
        prs = [_make_pr(number=1), _make_pr(number=2)]

        store.update(prs)
        diff = store.update(prs)

        assert diff.new_prs == []
        assert diff.closed_prs == []
        assert diff.updated_prs == []
        assert diff.has_changes is False


# ---------------------------------------------------------------------------
# PRStore — closed PRs
# ---------------------------------------------------------------------------


class TestClosedPrs:
    def test_removed_pr_appears_in_closed(self) -> None:
        store = PRStore()
        pr1 = _make_pr(number=1)
        pr2 = _make_pr(number=2)

        store.update([pr1, pr2])
        diff = store.update([pr1])  # pr2 removed

        assert diff.closed_prs == [pr2]
        assert diff.new_prs == []
        assert diff.updated_prs == []

    def test_all_prs_closed(self) -> None:
        store = PRStore()
        prs = [_make_pr(number=1), _make_pr(number=2)]

        store.update(prs)
        diff = store.update([])  # all gone

        assert len(diff.closed_prs) == 2
        assert diff.new_prs == []


# ---------------------------------------------------------------------------
# PRStore — updated PRs
# ---------------------------------------------------------------------------


class TestUpdatedPrs:
    def test_changed_updated_at_appears_in_updated(self) -> None:
        store = PRStore()
        pr_old = _make_pr(number=1, updated_at="2025-06-15T10:00:00Z")
        pr_new = _make_pr(number=1, updated_at="2025-06-15T12:00:00Z")

        store.update([pr_old])
        diff = store.update([pr_new])

        assert len(diff.updated_prs) == 1
        assert diff.updated_prs[0].updated_at == pr_new.updated_at
        assert diff.new_prs == []
        assert diff.closed_prs == []

    def test_same_updated_at_not_in_updated(self) -> None:
        store = PRStore()
        pr = _make_pr(number=1, updated_at="2025-06-15T10:00:00Z")

        store.update([pr])
        # Same PR with same timestamp but different title
        pr_same_time = _make_pr(number=1, title="New title", updated_at="2025-06-15T10:00:00Z")
        diff = store.update([pr_same_time])

        # Not detected as updated because updated_at is the same
        assert diff.updated_prs == []


# ---------------------------------------------------------------------------
# PRStore — mixed changes in one cycle
# ---------------------------------------------------------------------------


class TestMixedChanges:
    def test_new_closed_and_updated_in_one_cycle(self) -> None:
        store = PRStore()
        pr1 = _make_pr(number=1, updated_at="2025-06-15T10:00:00Z")
        pr2 = _make_pr(number=2)

        store.update([pr1, pr2])

        # pr1 updated, pr2 removed, pr3 new
        pr1_updated = _make_pr(number=1, updated_at="2025-06-15T12:00:00Z")
        pr3 = _make_pr(number=3)
        diff = store.update([pr1_updated, pr3])

        assert len(diff.new_prs) == 1
        assert diff.new_prs[0].number == 3

        assert len(diff.closed_prs) == 1
        assert diff.closed_prs[0].number == 2

        assert len(diff.updated_prs) == 1
        assert diff.updated_prs[0].number == 1


# ---------------------------------------------------------------------------
# PRStore — get_all
# ---------------------------------------------------------------------------


class TestGetAll:
    def test_returns_current_prs(self) -> None:
        store = PRStore()
        prs = [_make_pr(number=1), _make_pr(number=2)]
        store.update(prs)

        result = store.get_all()
        assert len(result) == 2
        urls = {pr.url for pr in result}
        assert "https://github.com/owner/repo/pull/1" in urls
        assert "https://github.com/owner/repo/pull/2" in urls

    def test_empty_store_returns_empty(self) -> None:
        store = PRStore()
        assert store.get_all() == []

    def test_reflects_latest_update(self) -> None:
        store = PRStore()
        store.update([_make_pr(number=1), _make_pr(number=2)])
        store.update([_make_pr(number=3)])

        result = store.get_all()
        assert len(result) == 1
        assert result[0].number == 3


# ---------------------------------------------------------------------------
# PRStore — get_status
# ---------------------------------------------------------------------------


class TestGetStatus:
    def test_initial_status(self) -> None:
        store = PRStore()
        status = store.get_status()

        assert status.pr_count == 0
        assert status.last_updated is None

    def test_status_after_update(self) -> None:
        store = PRStore()
        store.update([_make_pr(number=1), _make_pr(number=2)])
        status = store.get_status()

        assert status.pr_count == 2
        assert status.last_updated is not None
        assert isinstance(status.last_updated, datetime)
        # Should be a recent UTC timestamp
        assert status.last_updated.tzinfo is not None

    def test_status_reflects_latest_count(self) -> None:
        store = PRStore()
        store.update([_make_pr(number=1), _make_pr(number=2)])
        store.update([_make_pr(number=1)])
        status = store.get_status()

        assert status.pr_count == 1


# ---------------------------------------------------------------------------
# PRStore — clear
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear_empties_store(self) -> None:
        store = PRStore()
        store.update([_make_pr(number=1)])
        store.clear()

        assert store.get_all() == []
        status = store.get_status()
        assert status.pr_count == 0
        assert status.last_updated is None

    def test_update_after_clear_behaves_like_first_poll(self) -> None:
        store = PRStore()
        pr = _make_pr(number=1)
        store.update([pr])
        store.clear()

        # Same PR again — should appear as new (store was cleared)
        diff = store.update([pr])
        assert len(diff.new_prs) == 1
        assert diff.closed_prs == []
        assert diff.updated_prs == []
