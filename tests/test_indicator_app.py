"""Tests for forgewatch.indicator.app — the IndicatorApp orchestrator.

The GTK-dependent components (TrayIcon, PRWindow) are mocked at the
class level so these tests run in CI without system GTK packages.

The ``gi`` module (PyGObject) and its sub-modules are stubbed in
``sys.modules`` *before* any indicator imports so that ``tray.py`` and
``window.py`` can be imported in headless environments.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub out GTK / AppIndicator3 so tray.py and window.py are importable
# in CI where system GTK packages are not installed.
# ---------------------------------------------------------------------------
_gi_stub = MagicMock()
_gi_stub.require_version = MagicMock()

# Always override — real gi may already be loaded on GTK-enabled systems.
for _mod in ("gi", "gi.repository"):
    sys.modules[_mod] = _gi_stub  # type: ignore[assignment]

from forgewatch.indicator.models import DaemonStatus, PRInfo  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 3, 12, 0, 0, tzinfo=UTC)


def _make_pr(
    *,
    number: int = 42,
    repo: str = "owner/repo",
    title: str = "Fix login bug",
    review_requested: bool = False,
    assigned: bool = True,
) -> PRInfo:
    return PRInfo(
        url=f"https://github.com/{repo}/pull/{number}",
        title=title,
        repo=repo,
        author="octocat",
        author_avatar_url=f"https://avatars.githubusercontent.com/u/{number}",
        number=number,
        updated_at=_NOW,
        review_requested=review_requested,
        assigned=assigned,
    )


def _make_status(pr_count: int = 1) -> DaemonStatus:
    return DaemonStatus(pr_count=pr_count, last_updated=_NOW)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Patch paths — TrayIcon and PRWindow are lazy-imported inside __init__()
# from their source modules, so we patch at the source.  The gi module
# mock (below) ensures the source modules are importable in CI.
_PATCH_CLIENT = "forgewatch.indicator.app.DaemonClient"
_PATCH_TRAY = "forgewatch.indicator.tray.TrayIcon"
_PATCH_WINDOW = "forgewatch.indicator.window.PRWindow"
_PATCH_OPEN_URL = "forgewatch.indicator.app.open_url"


@pytest.fixture
def mock_client_cls():
    with patch(_PATCH_CLIENT) as cls:
        instance = MagicMock()
        instance.connect = AsyncMock()
        instance.disconnect = AsyncMock()
        instance.get_pull_requests = AsyncMock(return_value=[])
        instance.get_status = AsyncMock(return_value=None)
        instance.refresh = AsyncMock(return_value=[])
        instance.connected = False
        cls.return_value = instance
        yield cls


@pytest.fixture
def mock_tray_cls():
    with patch(_PATCH_TRAY) as cls:
        instance = MagicMock()
        cls.return_value = instance
        yield cls


@pytest.fixture
def mock_window_cls():
    with patch(_PATCH_WINDOW) as cls:
        instance = MagicMock()
        cls.return_value = instance
        yield cls


@pytest.fixture
def mock_open_url():
    with patch(_PATCH_OPEN_URL, new_callable=AsyncMock) as mock:
        yield mock


def _create_app(
    mock_client_cls: MagicMock,
    mock_tray_cls: MagicMock,
    mock_window_cls: MagicMock,
    *,
    icon_theme: str = "light",
    reconnect_interval: int = 10,
    window_width: int = 400,
    max_window_height: int = 500,
) -> tuple[Any, MagicMock, MagicMock, MagicMock]:
    """Import and create IndicatorApp with all GTK components mocked."""
    from forgewatch.indicator.app import IndicatorApp

    app = IndicatorApp(
        icon_theme=icon_theme,
        reconnect_interval=reconnect_interval,
        window_width=window_width,
        max_window_height=max_window_height,
    )
    # Return convenience references to the mock instances.
    client = mock_client_cls.return_value
    tray = mock_tray_cls.return_value
    window = mock_window_cls.return_value
    return app, client, tray, window


# ---------------------------------------------------------------------------
# Tests: Construction & wiring
# ---------------------------------------------------------------------------


class TestConstruction:
    """Verify the app creates components with correct callback wiring."""

    def test_creates_client_with_callbacks(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)
        mock_client_cls.assert_called_once()
        kwargs = mock_client_cls.call_args
        assert "on_prs_changed" in kwargs.kwargs
        assert "on_connection_changed" in kwargs.kwargs

    def test_creates_tray_with_callbacks(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)
        mock_tray_cls.assert_called_once()
        kwargs = mock_tray_cls.call_args
        assert "on_activate" in kwargs.kwargs
        assert "on_refresh" in kwargs.kwargs
        assert "on_quit" in kwargs.kwargs
        assert kwargs.kwargs["icon_theme"] == "light"

    def test_creates_tray_with_custom_icon_theme(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        _create_app(mock_client_cls, mock_tray_cls, mock_window_cls, icon_theme="dark")
        kwargs = mock_tray_cls.call_args
        assert kwargs.kwargs["icon_theme"] == "dark"

    def test_creates_window_with_callbacks(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)
        mock_window_cls.assert_called_once()
        kwargs = mock_window_cls.call_args
        assert "on_pr_clicked" in kwargs.kwargs
        assert "on_refresh" in kwargs.kwargs
        assert "on_visibility_changed" in kwargs.kwargs

    def test_passes_reconnect_interval_to_client(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        _create_app(mock_client_cls, mock_tray_cls, mock_window_cls, reconnect_interval=42)
        kwargs = mock_client_cls.call_args
        assert kwargs.kwargs["reconnect_interval"] == 42

    def test_passes_window_dimensions_to_window(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        _create_app(mock_client_cls, mock_tray_cls, mock_window_cls, window_width=600, max_window_height=800)
        kwargs = mock_window_cls.call_args
        assert kwargs.kwargs["window_width"] == 600
        assert kwargs.kwargs["max_window_height"] == 800


# ---------------------------------------------------------------------------
# Tests: run() lifecycle
# ---------------------------------------------------------------------------


class TestRun:
    """Verify the run() lifecycle: connect, initial fetch, shutdown."""

    async def test_run_connects_to_daemon(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        app, client, _tray, _window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)
        # Immediately signal shutdown so run() exits.
        app._shutdown_event.set()
        await app.run()
        client.connect.assert_awaited_once()

    async def test_run_fetches_initial_prs_when_connected(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        app, client, tray, window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)
        client.connected = True

        prs = [_make_pr()]
        status = _make_status(pr_count=1)
        client.get_pull_requests = AsyncMock(return_value=prs)
        client.get_status = AsyncMock(return_value=status)

        app._shutdown_event.set()
        await app.run()

        client.get_pull_requests.assert_awaited_once()
        client.get_status.assert_awaited_once()
        tray.set_pr_count.assert_called_with(1, has_review_requested=False)
        window.update_prs.assert_called_with(prs, status)

    async def test_run_skips_fetch_when_disconnected(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        app, client, _tray, _window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)
        client.connected = False

        app._shutdown_event.set()
        await app.run()

        client.get_pull_requests.assert_not_awaited()

    async def test_run_with_review_requested_prs(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        app, client, tray, _window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)
        client.connected = True

        prs = [_make_pr(review_requested=True)]
        client.get_pull_requests = AsyncMock(return_value=prs)
        client.get_status = AsyncMock(return_value=_make_status(pr_count=1))

        app._shutdown_event.set()
        await app.run()

        tray.set_pr_count.assert_called_with(1, has_review_requested=True)

    async def test_run_initial_pr_fetch_failure(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        """If the initial PR fetch fails, run() should still complete cleanly."""
        app, client, tray, window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)
        client.connected = True
        client.get_pull_requests = AsyncMock(side_effect=ConnectionError("lost"))

        app._shutdown_event.set()
        await app.run()

        # The error should be caught — tray and window should NOT be updated
        # because _fetch_and_update returns early after the exception.
        tray.set_pr_count.assert_not_called()
        window.update_prs.assert_not_called()

    async def test_run_initial_status_fetch_failure(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        """If the initial status fetch fails, cached status (None) should be used."""
        app, client, tray, window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)
        client.connected = True

        prs = [_make_pr()]
        client.get_pull_requests = AsyncMock(return_value=prs)
        client.get_status = AsyncMock(side_effect=ConnectionError("lost"))

        app._shutdown_event.set()
        await app.run()

        # UI should still be updated — with None status from fallback.
        tray.set_pr_count.assert_called_with(1, has_review_requested=False)
        window.update_prs.assert_called_with(prs, None)


# ---------------------------------------------------------------------------
# Tests: shutdown()
# ---------------------------------------------------------------------------


class TestShutdown:
    """Verify clean shutdown behaviour."""

    async def test_shutdown_disconnects_client(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        app, client, _tray, _window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)
        await app.shutdown()
        client.disconnect.assert_awaited_once()

    async def test_shutdown_cancels_pending_tasks(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        app, _client, _tray, _window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)

        # Simulate a pending background coroutine.
        barrier = asyncio.Event()

        async def blocked() -> None:
            await barrier.wait()

        app._schedule(blocked())
        assert len(app._tasks) == 1
        task = next(iter(app._tasks))

        await app.shutdown()

        # cancel() requests cancellation; the task transitions to
        # "cancelled" once the event loop processes the CancelledError.
        await asyncio.sleep(0)
        assert task.cancelled()


# ---------------------------------------------------------------------------
# Tests: _on_prs_changed callback
# ---------------------------------------------------------------------------


class TestOnPrsChanged:
    """Verify that PullRequestsChanged signals update tray and window."""

    async def test_updates_tray_and_window(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        app, client, tray, window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)
        prs = [_make_pr(), _make_pr(number=99, review_requested=True)]
        status = _make_status(pr_count=2)
        client.get_status = AsyncMock(return_value=status)

        app._on_prs_changed(prs)
        # Let the scheduled task run.
        await asyncio.sleep(0)

        tray.set_pr_count.assert_called_with(2, has_review_requested=True)
        window.update_prs.assert_called_with(prs, status)

    async def test_caches_prs(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        app, client, _tray, _window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)
        prs = [_make_pr()]
        client.get_status = AsyncMock(return_value=None)

        app._on_prs_changed(prs)
        await asyncio.sleep(0)

        assert app._current_prs is prs

    async def test_uses_cached_status_on_failure(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        app, client, _tray, window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)
        cached_status = _make_status(pr_count=5)
        app._current_status = cached_status
        client.get_status = AsyncMock(side_effect=ConnectionError("lost"))

        prs = [_make_pr()]
        app._on_prs_changed(prs)
        await asyncio.sleep(0)

        # Should fall back to cached status.
        window.update_prs.assert_called_with(prs, cached_status)


# ---------------------------------------------------------------------------
# Tests: _on_connection_changed callback
# ---------------------------------------------------------------------------


class TestOnConnectionChanged:
    """Verify connection state changes update the UI correctly."""

    def test_disconnected_updates_tray_and_window(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        app, _client, tray, window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)

        app._on_connection_changed(connected=False)

        tray.set_connected.assert_called_with(connected=False)
        tray.set_pr_count.assert_called_with(0, has_review_requested=False)
        window.set_disconnected.assert_called_once()

    def test_disconnected_clears_cached_state(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        app, _client, _tray, _window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)
        app._current_prs = [_make_pr()]
        app._current_status = _make_status()

        app._on_connection_changed(connected=False)

        assert app._current_prs == []
        assert app._current_status is None

    async def test_connected_fetches_and_updates(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        app, client, tray, window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)
        prs = [_make_pr(review_requested=True)]
        status = _make_status(pr_count=1)
        client.get_pull_requests = AsyncMock(return_value=prs)
        client.get_status = AsyncMock(return_value=status)

        app._on_connection_changed(connected=True)
        tray.set_connected.assert_called_with(connected=True)

        # Let the scheduled async task run.
        await asyncio.sleep(0)

        client.get_pull_requests.assert_awaited_once()
        tray.set_pr_count.assert_called_with(1, has_review_requested=True)
        window.update_prs.assert_called_with(prs, status)


# ---------------------------------------------------------------------------
# Tests: UI action callbacks
# ---------------------------------------------------------------------------


class TestActivate:
    """Verify tray activate toggles the window."""

    def test_toggles_window(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        app, _client, _tray, window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)

        app._on_activate()

        window.toggle.assert_called_once()


class TestWindowVisibilityChanged:
    """Verify the window visibility callback updates the tray."""

    def test_updates_tray_on_visible(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        app, _client, tray, _window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)

        app._on_window_visibility_changed(True)  # noqa: FBT003

        tray.set_window_visible.assert_called_once_with(visible=True)

    def test_updates_tray_on_hidden(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        app, _client, tray, _window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)

        app._on_window_visibility_changed(False)  # noqa: FBT003

        tray.set_window_visible.assert_called_once_with(visible=False)


class TestRefresh:
    """Verify refresh triggers a daemon poll and UI update."""

    async def test_refresh_when_connected(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        app, client, tray, window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)
        client.connected = True

        prs = [_make_pr()]
        status = _make_status(pr_count=1)
        client.refresh = AsyncMock(return_value=prs)
        client.get_status = AsyncMock(return_value=status)

        app._on_refresh()
        await asyncio.sleep(0)

        client.refresh.assert_awaited_once()
        tray.set_pr_count.assert_called_with(1, has_review_requested=False)
        window.update_prs.assert_called_with(prs, status)

    def test_refresh_when_disconnected_is_noop(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        app, client, _tray, _window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)
        client.connected = False

        app._on_refresh()

        # No task should have been scheduled.
        assert len(app._tasks) == 0

    async def test_refresh_failure_does_not_crash(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        """If client.refresh() raises, the error is logged but not propagated."""
        app, client, tray, window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)
        client.connected = True
        client.refresh = AsyncMock(side_effect=ConnectionError("pipe broken"))

        app._on_refresh()
        await asyncio.sleep(0)

        # The UI should NOT be updated since refresh failed.
        tray.set_pr_count.assert_not_called()
        window.update_prs.assert_not_called()

    async def test_refresh_status_fetch_failure_uses_cache(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        """If status fetch fails after refresh, cached status is used."""
        app, client, _tray, window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)
        client.connected = True

        cached_status = _make_status(pr_count=3)
        app._current_status = cached_status

        prs = [_make_pr()]
        client.refresh = AsyncMock(return_value=prs)
        client.get_status = AsyncMock(side_effect=ConnectionError("lost"))

        app._on_refresh()
        await asyncio.sleep(0)

        # UI should be updated with cached status as fallback.
        window.update_prs.assert_called_with(prs, cached_status)


class TestPrClicked:
    """Verify PR click opens URL and hides window."""

    async def test_opens_url_and_hides_window(
        self,
        mock_client_cls: MagicMock,
        mock_tray_cls: MagicMock,
        mock_window_cls: MagicMock,
        mock_open_url: AsyncMock,
    ) -> None:
        app, _client, _tray, window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)

        app._on_pr_clicked("https://github.com/owner/repo/pull/42")

        # Window should be hidden immediately (synchronous).
        window.hide.assert_called_once()

        # Let the async open_url task run.
        await asyncio.sleep(0)
        mock_open_url.assert_awaited_once_with("https://github.com/owner/repo/pull/42")

    async def test_open_url_failure_does_not_crash(
        self,
        mock_client_cls: MagicMock,
        mock_tray_cls: MagicMock,
        mock_window_cls: MagicMock,
        mock_open_url: AsyncMock,
    ) -> None:
        """If open_url raises, the error is logged but not propagated."""
        app, _client, _tray, window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)
        mock_open_url.side_effect = OSError("no browser")

        app._on_pr_clicked("https://github.com/owner/repo/pull/42")
        window.hide.assert_called_once()

        # Let the async task run — should not raise.
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        # Task should be cleaned up despite the error.
        assert len(app._tasks) == 0


class TestQuit:
    """Verify quit sets the shutdown event."""

    def test_sets_shutdown_event(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        app, _client, _tray, _window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)

        assert not app._shutdown_event.is_set()
        app._on_quit()
        assert app._shutdown_event.is_set()


# ---------------------------------------------------------------------------
# Tests: _schedule and _task_done helpers
# ---------------------------------------------------------------------------


class TestSchedule:
    """Verify task scheduling and cleanup."""

    async def test_task_tracked_during_execution(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        app, _client, _tray, _window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)

        barrier = asyncio.Event()

        async def slow_coro() -> None:
            await barrier.wait()

        app._schedule(slow_coro())
        assert len(app._tasks) == 1

        barrier.set()
        # Two iterations: one for the coro to complete, one for the done callback.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert len(app._tasks) == 0

    async def test_task_removed_after_completion(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        app, _client, _tray, _window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)

        async def noop() -> None:
            pass

        app._schedule(noop())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert len(app._tasks) == 0

    async def test_exception_logged_not_raised(
        self, mock_client_cls: MagicMock, mock_tray_cls: MagicMock, mock_window_cls: MagicMock
    ) -> None:
        app, _client, _tray, _window = _create_app(mock_client_cls, mock_tray_cls, mock_window_cls)

        async def failing() -> None:
            msg = "boom"
            raise RuntimeError(msg)

        # Should not propagate — the task_done callback logs it.
        app._schedule(failing())
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        # Task should still be cleaned up.
        assert len(app._tasks) == 0
