"""Tests for github_monitor.cli._output."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from github_monitor.cli import _output
from github_monitor.cli._output import _BLUE, _GREEN, _RED, _RESET, _YELLOW, err, info, ok, step, warn

if TYPE_CHECKING:
    import pytest

# ---------------------------------------------------------------------------
# _fmt — colour formatting
# ---------------------------------------------------------------------------


class TestFmt:
    """Tests for the _fmt() helper."""

    def test_returns_coloured_string_when_stdout_colour_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_output, "_SUPPORTS_STDOUT_COLOR", True)
        result = _output._fmt(_BLUE, "[INFO]")
        assert result == f"{_BLUE}[INFO]{_RESET}"

    def test_returns_plain_string_when_stdout_colour_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_output, "_SUPPORTS_STDOUT_COLOR", False)
        result = _output._fmt(_BLUE, "[INFO]")
        assert result == "[INFO]"

    def test_uses_stderr_flag_for_colour_decision(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_output, "_SUPPORTS_STDOUT_COLOR", False)
        monkeypatch.setattr(_output, "_SUPPORTS_STDERR_COLOR", True)
        result = _output._fmt(_RED, "[ERR]", stderr=True)
        assert result == f"{_RED}[ERR]{_RESET}"

    def test_stderr_colour_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_output, "_SUPPORTS_STDERR_COLOR", False)
        result = _output._fmt(_RED, "[ERR]", stderr=True)
        assert result == "[ERR]"


# ---------------------------------------------------------------------------
# Output functions — content verification (colour-independent)
# ---------------------------------------------------------------------------


class TestInfoOutput:
    """Tests for the info() function."""

    def test_writes_to_stdout_with_info_prefix(self) -> None:
        mock_stdout = MagicMock()
        with patch.object(_output.sys, "stdout", mock_stdout):
            info("hello world")
        written = mock_stdout.write.call_args[0][0]
        assert "[INFO]" in written
        assert "hello world" in written
        assert written.endswith("\n")


class TestOkOutput:
    """Tests for the ok() function."""

    def test_writes_to_stdout_with_ok_prefix(self) -> None:
        mock_stdout = MagicMock()
        with patch.object(_output.sys, "stdout", mock_stdout):
            ok("all good")
        written = mock_stdout.write.call_args[0][0]
        assert "[OK]" in written
        assert "all good" in written
        assert written.endswith("\n")


class TestWarnOutput:
    """Tests for the warn() function."""

    def test_writes_to_stderr_with_warn_prefix(self) -> None:
        mock_stderr = MagicMock()
        with patch.object(_output.sys, "stderr", mock_stderr):
            warn("careful")
        written = mock_stderr.write.call_args[0][0]
        assert "[WARN]" in written
        assert "careful" in written
        assert written.endswith("\n")


class TestErrOutput:
    """Tests for the err() function."""

    def test_writes_to_stderr_with_err_prefix(self) -> None:
        mock_stderr = MagicMock()
        with patch.object(_output.sys, "stderr", mock_stderr):
            err("something broke")
        written = mock_stderr.write.call_args[0][0]
        assert "[ERR]" in written
        assert "something broke" in written
        assert written.endswith("\n")


class TestStepOutput:
    """Tests for the step() function."""

    def test_writes_to_stdout_with_step_counter(self) -> None:
        mock_stdout = MagicMock()
        with patch.object(_output.sys, "stdout", mock_stdout):
            step(2, 5, "installing deps")
        written = mock_stdout.write.call_args[0][0]
        assert "[2/5]" in written
        assert "installing deps" in written
        assert written.endswith("\n")

    def test_step_counter_formatting(self) -> None:
        mock_stdout = MagicMock()
        with patch.object(_output.sys, "stdout", mock_stdout):
            step(10, 10, "done")
        written = mock_stdout.write.call_args[0][0]
        assert "[10/10]" in written


# ---------------------------------------------------------------------------
# Output functions — colour rendering
# ---------------------------------------------------------------------------


class TestColouredOutput:
    """Tests verifying ANSI codes are included when colour is enabled."""

    def test_info_includes_blue_when_colour_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_output, "_SUPPORTS_STDOUT_COLOR", True)
        mock_stdout = MagicMock()
        with patch.object(_output.sys, "stdout", mock_stdout):
            info("test")
        written = mock_stdout.write.call_args[0][0]
        assert _BLUE in written
        assert _RESET in written

    def test_ok_includes_green_when_colour_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_output, "_SUPPORTS_STDOUT_COLOR", True)
        mock_stdout = MagicMock()
        with patch.object(_output.sys, "stdout", mock_stdout):
            ok("test")
        written = mock_stdout.write.call_args[0][0]
        assert _GREEN in written

    def test_warn_includes_yellow_when_colour_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_output, "_SUPPORTS_STDERR_COLOR", True)
        mock_stderr = MagicMock()
        with patch.object(_output.sys, "stderr", mock_stderr):
            warn("test")
        written = mock_stderr.write.call_args[0][0]
        assert _YELLOW in written

    def test_err_includes_red_when_colour_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_output, "_SUPPORTS_STDERR_COLOR", True)
        mock_stderr = MagicMock()
        with patch.object(_output.sys, "stderr", mock_stderr):
            err("test")
        written = mock_stderr.write.call_args[0][0]
        assert _RED in written


class TestPlainOutput:
    """Tests verifying ANSI codes are absent when colour is disabled."""

    def test_info_no_ansi_when_colour_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_output, "_SUPPORTS_STDOUT_COLOR", False)
        mock_stdout = MagicMock()
        with patch.object(_output.sys, "stdout", mock_stdout):
            info("test")
        written = mock_stdout.write.call_args[0][0]
        assert "\033[" not in written

    def test_warn_no_ansi_when_colour_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_output, "_SUPPORTS_STDERR_COLOR", False)
        mock_stderr = MagicMock()
        with patch.object(_output.sys, "stderr", mock_stderr):
            warn("test")
        written = mock_stderr.write.call_args[0][0]
        assert "\033[" not in written

    def test_step_no_ansi_when_colour_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_output, "_SUPPORTS_STDOUT_COLOR", False)
        mock_stdout = MagicMock()
        with patch.object(_output.sys, "stdout", mock_stdout):
            step(1, 3, "test")
        written = mock_stdout.write.call_args[0][0]
        assert "\033[" not in written
        assert written == "[1/3] test\n"
