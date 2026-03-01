"""Tests for github_monitor.dbus_service."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

from github_monitor.dbus_service import (
    BUS_NAME,
    INTERFACE_NAME,
    OBJECT_PATH,
    GithubMonitorInterface,
    _serialize_pr,
    _serialize_prs,
    _serialize_status,
    setup_dbus,
)
from github_monitor.poller import PullRequest
from github_monitor.store import PRStore, StoreStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)


def _make_pr(
    number: int = 1,
    repo: str = "owner/repo",
    *,
    title: str = "Fix bug",
    updated_at: datetime = _NOW,
    review_requested: bool = True,
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
        updated_at=updated_at,
        review_requested=review_requested,
        assigned=False,
    )


def _unwrap_method(bound_method: Any) -> Any:
    """Access the original function behind a dbus-next @method wrapper."""
    return bound_method.__func__.__wrapped__


def _unwrap_signal(bound_method: Any) -> Any:
    """Access the original function behind a dbus-next @signal wrapper."""
    return bound_method.__func__.__wrapped__


def _make_interface(
    store: PRStore | None = None,
    poll_callback: Callable[[], Awaitable[None]] | None = None,
) -> GithubMonitorInterface:
    """Build a GithubMonitorInterface with optional overrides."""
    if store is None:
        store = PRStore()
    if poll_callback is None:
        poll_callback = AsyncMock()
    return GithubMonitorInterface(store, poll_callback)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_bus_name(self) -> None:
        assert BUS_NAME == "org.github_monitor.Daemon"

    def test_object_path(self) -> None:
        assert OBJECT_PATH == "/org/github_monitor/Daemon"

    def test_interface_name(self) -> None:
        assert INTERFACE_NAME == "org.github_monitor.Daemon"


# ---------------------------------------------------------------------------
# Serialisation — _serialize_pr
# ---------------------------------------------------------------------------


class TestSerializePr:
    def test_all_fields_present(self) -> None:
        pr = _make_pr(number=42, title="Add feature", repo="org/project")
        result = _serialize_pr(pr)

        assert result["url"] == "https://github.com/org/project/pull/42"
        assert result["title"] == "Add feature"
        assert result["repo"] == "org/project"
        assert result["author"] == "alice"
        assert result["number"] == 42
        assert result["review_requested"] is True
        assert result["assigned"] is False

    def test_updated_at_is_iso_string(self) -> None:
        pr = _make_pr(updated_at=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC))
        result = _serialize_pr(pr)

        assert result["updated_at"] == "2025-01-15T10:30:00+00:00"

    def test_both_flags_true(self) -> None:
        pr = PullRequest(
            url="https://github.com/owner/repo/pull/1",
            api_url="https://api.github.com/repos/owner/repo/pulls/1",
            title="Fix bug",
            repo_full_name="owner/repo",
            author="alice",
            author_avatar_url="https://avatars.githubusercontent.com/u/1",
            number=1,
            updated_at=_NOW,
            review_requested=True,
            assigned=True,
        )
        result = _serialize_pr(pr)

        assert result["review_requested"] is True
        assert result["assigned"] is True


# ---------------------------------------------------------------------------
# Serialisation — _serialize_prs
# ---------------------------------------------------------------------------


class TestSerializePrs:
    def test_empty_list(self) -> None:
        result = _serialize_prs([])
        assert json.loads(result) == []

    def test_multiple_prs(self) -> None:
        prs = [_make_pr(number=1), _make_pr(number=2)]
        result = json.loads(_serialize_prs(prs))

        assert len(result) == 2
        numbers = {pr["number"] for pr in result}
        assert numbers == {1, 2}

    def test_output_is_valid_json(self) -> None:
        prs = [_make_pr(number=1)]
        result = _serialize_prs(prs)

        # Should not raise
        parsed = json.loads(result)
        assert isinstance(parsed, list)


# ---------------------------------------------------------------------------
# Serialisation — _serialize_status
# ---------------------------------------------------------------------------


class TestSerializeStatus:
    def test_with_timestamp(self) -> None:
        status = StoreStatus(pr_count=5, last_updated=_NOW)
        result = json.loads(_serialize_status(status))

        assert result["pr_count"] == 5
        assert result["last_updated"] == "2025-06-15T10:00:00+00:00"

    def test_with_none_timestamp(self) -> None:
        status = StoreStatus(pr_count=0, last_updated=None)
        result = json.loads(_serialize_status(status))

        assert result["pr_count"] == 0
        assert result["last_updated"] is None

    def test_output_is_valid_json(self) -> None:
        status = StoreStatus(pr_count=3, last_updated=_NOW)
        result = _serialize_status(status)

        parsed = json.loads(result)
        assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# GithubMonitorInterface — construction
# ---------------------------------------------------------------------------


class TestInterfaceConstruction:
    def test_creates_with_correct_interface_name(self) -> None:
        iface = _make_interface()
        assert iface.name == INTERFACE_NAME

    def test_stores_references(self) -> None:
        store = PRStore()
        callback = AsyncMock()
        iface = GithubMonitorInterface(store, callback)

        assert iface._store is store
        assert iface._poll_callback is callback


# ---------------------------------------------------------------------------
# GithubMonitorInterface — GetPullRequests
# ---------------------------------------------------------------------------


class TestGetPullRequests:
    def test_empty_store_returns_empty_array(self) -> None:
        iface = _make_interface()
        result = _unwrap_method(iface.GetPullRequests)(iface)

        assert json.loads(result) == []

    def test_returns_all_store_prs(self) -> None:
        store = PRStore()
        store.update([_make_pr(number=1), _make_pr(number=2)])
        iface = _make_interface(store=store)

        result = json.loads(_unwrap_method(iface.GetPullRequests)(iface))

        assert len(result) == 2
        numbers = {pr["number"] for pr in result}
        assert numbers == {1, 2}

    def test_returns_json_string(self) -> None:
        store = PRStore()
        store.update([_make_pr(number=1)])
        iface = _make_interface(store=store)

        result = _unwrap_method(iface.GetPullRequests)(iface)

        assert isinstance(result, str)
        json.loads(result)  # should not raise


# ---------------------------------------------------------------------------
# GithubMonitorInterface — GetStatus
# ---------------------------------------------------------------------------


class TestGetStatus:
    def test_initial_status(self) -> None:
        iface = _make_interface()
        result = json.loads(_unwrap_method(iface.GetStatus)(iface))

        assert result["pr_count"] == 0
        assert result["last_updated"] is None

    def test_status_after_update(self) -> None:
        store = PRStore()
        store.update([_make_pr(number=1), _make_pr(number=2)])
        iface = _make_interface(store=store)

        result = json.loads(_unwrap_method(iface.GetStatus)(iface))

        assert result["pr_count"] == 2
        assert result["last_updated"] is not None


# ---------------------------------------------------------------------------
# GithubMonitorInterface — Refresh
# ---------------------------------------------------------------------------


class TestRefresh:
    async def test_calls_poll_callback(self) -> None:
        callback = AsyncMock()
        iface = _make_interface(poll_callback=callback)

        await _unwrap_method(iface.Refresh)(iface)

        callback.assert_awaited_once()

    async def test_returns_updated_prs(self) -> None:
        store = PRStore()
        pr = _make_pr(number=42)

        async def poll_and_update() -> None:
            store.update([pr])

        iface = _make_interface(store=store, poll_callback=poll_and_update)

        result = await _unwrap_method(iface.Refresh)(iface)

        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["number"] == 42

    async def test_returns_empty_when_no_prs(self) -> None:
        callback = AsyncMock()
        iface = _make_interface(poll_callback=callback)

        result = await _unwrap_method(iface.Refresh)(iface)

        assert json.loads(result) == []


# ---------------------------------------------------------------------------
# GithubMonitorInterface — PullRequestsChanged signal
# ---------------------------------------------------------------------------


class TestPullRequestsChangedSignal:
    def test_returns_current_prs_json(self) -> None:
        store = PRStore()
        store.update([_make_pr(number=1), _make_pr(number=2)])
        iface = _make_interface(store=store)

        result = _unwrap_signal(iface.PullRequestsChanged)(iface)

        parsed = json.loads(result)
        assert len(parsed) == 2

    def test_returns_empty_when_no_prs(self) -> None:
        iface = _make_interface()

        result = _unwrap_signal(iface.PullRequestsChanged)(iface)

        assert json.loads(result) == []

    def test_reflects_latest_state(self) -> None:
        store = PRStore()
        store.update([_make_pr(number=1)])
        iface = _make_interface(store=store)

        # Update store — signal should reflect new state
        store.update([_make_pr(number=2), _make_pr(number=3)])

        result = _unwrap_signal(iface.PullRequestsChanged)(iface)

        parsed = json.loads(result)
        assert len(parsed) == 2
        numbers = {pr["number"] for pr in parsed}
        assert numbers == {2, 3}


# ---------------------------------------------------------------------------
# setup_dbus
# ---------------------------------------------------------------------------


class TestSetupDbus:
    async def test_connects_and_exports(self) -> None:
        mock_bus = MagicMock()
        mock_bus.export = MagicMock()
        mock_bus.request_name = AsyncMock()

        mock_bus_class = MagicMock()
        mock_bus_class.return_value.connect = AsyncMock(return_value=mock_bus)

        with patch(
            "github_monitor.dbus_service.MessageBus",
            mock_bus_class,
        ):
            store = PRStore()
            callback = AsyncMock()
            bus, interface = await setup_dbus(store, callback)

        assert bus is mock_bus
        assert isinstance(interface, GithubMonitorInterface)

    async def test_exports_at_correct_path(self) -> None:
        mock_bus = MagicMock()
        mock_bus.export = MagicMock()
        mock_bus.request_name = AsyncMock()

        mock_bus_class = MagicMock()
        mock_bus_class.return_value.connect = AsyncMock(return_value=mock_bus)

        with patch(
            "github_monitor.dbus_service.MessageBus",
            mock_bus_class,
        ):
            await setup_dbus(PRStore(), AsyncMock())

        mock_bus.export.assert_called_once()
        call_args = mock_bus.export.call_args
        assert call_args[0][0] == OBJECT_PATH
        assert isinstance(call_args[0][1], GithubMonitorInterface)

    async def test_requests_correct_bus_name(self) -> None:
        mock_bus = MagicMock()
        mock_bus.export = MagicMock()
        mock_bus.request_name = AsyncMock()

        mock_bus_class = MagicMock()
        mock_bus_class.return_value.connect = AsyncMock(return_value=mock_bus)

        with patch(
            "github_monitor.dbus_service.MessageBus",
            mock_bus_class,
        ):
            await setup_dbus(PRStore(), AsyncMock())

        mock_bus.request_name.assert_awaited_once_with(BUS_NAME)
