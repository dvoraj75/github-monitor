"""Tests for forgewatch.indicator.__main__ — dependency checks and entry point.

The indicator entry point validates that GTK3, AppIndicator3, and gbulb
are available before launching.  These tests mock the import system and
verify every branch in ``_check_dependencies()`` and ``main()``.
"""

from __future__ import annotations

import builtins
import importlib
import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from types import ModuleType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_import() -> ModuleType:
    """Import (or re-import) the indicator __main__ module cleanly.

    Forces a fresh import so that top-level side effects and the
    ``_check_dependencies`` closure capture fresh mocks each time.
    """
    mod_name = "forgewatch.indicator.__main__"
    # Remove from cache so the module re-executes on import.
    sys.modules.pop(mod_name, None)
    return importlib.import_module(mod_name)


# ---------------------------------------------------------------------------
# _check_dependencies
# ---------------------------------------------------------------------------


class TestCheckDependenciesAllPresent:
    """When all dependencies are available, _check_dependencies returns True."""

    def test_returns_true(self) -> None:
        gi_mock = MagicMock()
        gi_mock.require_version = MagicMock()  # no error
        gbulb_mock = MagicMock()

        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "gi":
                return gi_mock
            if name == "gbulb":
                return gbulb_mock
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            mod = _fresh_import()
            assert mod._check_dependencies() is True


class TestCheckDependenciesMissingGi:
    """Missing PyGObject (gi) should return False."""

    def test_returns_false(self) -> None:
        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "gi":
                msg = "No module named 'gi'"
                raise ImportError(msg)
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            mod = _fresh_import()
            assert mod._check_dependencies() is False

    def test_prints_help_to_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "gi":
                msg = "No module named 'gi'"
                raise ImportError(msg)
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            mod = _fresh_import()
            mod._check_dependencies()
            captured = capsys.readouterr()
            assert "system packages" in captured.err.lower() or "GTK3" in captured.err


class TestCheckDependenciesMissingGtk:
    """Missing GTK 3.0 typelib should return False."""

    def test_returns_false(self) -> None:
        gi_mock = MagicMock()
        gbulb_mock = MagicMock()
        call_count = 0

        def require_version(namespace: str, version: str) -> None:
            nonlocal call_count
            call_count += 1
            if namespace == "Gtk":
                msg = "Namespace Gtk not available"
                raise ValueError(msg)

        gi_mock.require_version = require_version

        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "gi":
                return gi_mock
            if name == "gbulb":
                return gbulb_mock
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            mod = _fresh_import()
            assert mod._check_dependencies() is False


class TestCheckDependenciesMissingAppIndicator:
    """Missing AppIndicator3 typelib should return False."""

    def test_returns_false(self) -> None:
        gi_mock = MagicMock()
        gbulb_mock = MagicMock()

        def require_version(namespace: str, version: str) -> None:
            if namespace == "AppIndicator3":
                msg = "Namespace AppIndicator3 not available"
                raise ValueError(msg)

        gi_mock.require_version = require_version

        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "gi":
                return gi_mock
            if name == "gbulb":
                return gbulb_mock
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            mod = _fresh_import()
            assert mod._check_dependencies() is False


class TestCheckDependenciesMissingGbulb:
    """Missing gbulb package should return False."""

    def test_returns_false(self) -> None:
        gi_mock = MagicMock()
        gi_mock.require_version = MagicMock()

        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "gi":
                return gi_mock
            if name == "gbulb":
                msg = "No module named 'gbulb'"
                raise ImportError(msg)
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            mod = _fresh_import()
            assert mod._check_dependencies() is False

    def test_prints_gbulb_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        gi_mock = MagicMock()
        gi_mock.require_version = MagicMock()

        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "gi":
                return gi_mock
            if name == "gbulb":
                msg = "No module named 'gbulb'"
                raise ImportError(msg)
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            mod = _fresh_import()
            mod._check_dependencies()
            captured = capsys.readouterr()
            assert "gbulb" in captured.err


class TestCheckDependenciesMultipleMissing:
    """Multiple missing dependencies should all be reported, returning False."""

    def test_gtk_and_gbulb_both_missing(self) -> None:
        gi_mock = MagicMock()

        def require_version(namespace: str, version: str) -> None:
            if namespace == "Gtk":
                msg = "Namespace Gtk not available"
                raise ValueError(msg)

        gi_mock.require_version = require_version

        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "gi":
                return gi_mock
            if name == "gbulb":
                msg = "No module named 'gbulb'"
                raise ImportError(msg)
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            mod = _fresh_import()
            assert mod._check_dependencies() is False


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


class TestMainExitsOnFailedDeps:
    """main() should sys.exit(1) when dependencies are missing."""

    def test_exits_with_code_1(self) -> None:
        mod = _fresh_import()

        with (
            patch.object(mod, "_check_dependencies", return_value=False),
            pytest.raises(SystemExit, match="1"),
        ):
            mod.main()


class TestMainRunsApp:
    """main() should launch IndicatorApp when deps are present."""

    def test_runs_indicator_app(self) -> None:
        mod = _fresh_import()

        mock_app = MagicMock()
        mock_app_class = MagicMock(return_value=mock_app)
        mock_gbulb = MagicMock()
        mock_loop = MagicMock()

        # Mock the deferred imports that happen inside main():
        #   - ``from forgewatch.config import load_config``
        #   - ``import gbulb``
        #   - ``from .app import IndicatorApp``
        mock_config_mod = MagicMock()
        mock_config_mod.load_config.side_effect = Exception("no config")
        mock_app_mod = MagicMock()
        mock_app_mod.IndicatorApp = mock_app_class

        with (
            patch.object(mod, "_check_dependencies", return_value=True),
            patch("sys.argv", ["indicator"]),
            patch.dict(
                "sys.modules",
                {
                    "gbulb": mock_gbulb,
                    "forgewatch.config": mock_config_mod,
                    "forgewatch.indicator.app": mock_app_mod,
                },
            ),
            patch("asyncio.new_event_loop", return_value=mock_loop),
        ):
            mod.main()

        mock_gbulb.install.assert_called_once()
        mock_loop.run_until_complete.assert_called()
        mock_loop.close.assert_called_once()


class TestMainVerboseFlag:
    """main() with --verbose should set DEBUG logging."""

    def test_sets_debug_level(self) -> None:
        import logging

        mod = _fresh_import()

        mock_app = MagicMock()
        mock_gbulb = MagicMock()
        mock_loop = MagicMock()
        mock_config_mod = MagicMock()
        mock_config_mod.load_config.side_effect = Exception("no config")
        mock_app_mod = MagicMock()
        mock_app_mod.IndicatorApp = MagicMock(return_value=mock_app)

        with (
            patch.object(mod, "_check_dependencies", return_value=True),
            patch("sys.argv", ["indicator", "--verbose"]),
            patch.dict(
                "sys.modules",
                {
                    "gbulb": mock_gbulb,
                    "forgewatch.config": mock_config_mod,
                    "forgewatch.indicator.app": mock_app_mod,
                },
            ),
            patch("asyncio.new_event_loop", return_value=mock_loop),
            patch("logging.basicConfig") as mock_basic_config,
        ):
            mod.main()

        mock_basic_config.assert_called_once()
        assert mock_basic_config.call_args[1]["level"] == logging.DEBUG


class TestMainConfigLoadFailure:
    """main() should use default 'light' theme when config loading fails."""

    def test_uses_default_icon_theme(self) -> None:
        mod = _fresh_import()

        mock_app_class = MagicMock()
        mock_gbulb = MagicMock()
        mock_loop = MagicMock()
        mock_config_mod = MagicMock()
        mock_config_mod.load_config.side_effect = Exception("no config file")
        mock_config_mod.IndicatorConfig.return_value = MagicMock(
            reconnect_interval=10,
            window_width=400,
            max_window_height=500,
        )
        mock_app_mod = MagicMock()
        mock_app_mod.IndicatorApp = mock_app_class

        with (
            patch.object(mod, "_check_dependencies", return_value=True),
            patch("sys.argv", ["indicator"]),
            patch.dict(
                "sys.modules",
                {
                    "gbulb": mock_gbulb,
                    "forgewatch.config": mock_config_mod,
                    "forgewatch.indicator.app": mock_app_mod,
                },
            ),
            patch("asyncio.new_event_loop", return_value=mock_loop),
        ):
            mod.main()

        # IndicatorApp should be constructed with icon_theme="light" (the default)
        # and default indicator config values.
        mock_app_class.assert_called_once()
        call_kwargs = mock_app_class.call_args.kwargs
        assert call_kwargs["icon_theme"] == "light"
        assert call_kwargs["reconnect_interval"] == 10
        assert call_kwargs["window_width"] == 400
        assert call_kwargs["max_window_height"] == 500
