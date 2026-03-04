"""Tests for github_monitor.cli._prompts."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from github_monitor.cli._prompts import _read_input, ask_int, ask_list, ask_string, ask_yes_no

# ---------------------------------------------------------------------------
# _read_input — low-level input wrapper
# ---------------------------------------------------------------------------


class TestReadInput:
    """Tests for the _read_input() helper."""

    def test_returns_user_input(self) -> None:
        with patch("builtins.input", return_value="hello"):
            assert _read_input("prompt: ") == "hello"

    def test_passes_prompt_to_builtin_input(self) -> None:
        mock_input = MagicMock(return_value="x")
        with patch("builtins.input", mock_input):
            _read_input("Enter value: ")
        mock_input.assert_called_once_with("Enter value: ")

    def test_eof_error_causes_sys_exit(self) -> None:
        with (
            patch("builtins.input", side_effect=EOFError),
            patch("github_monitor.cli._prompts.sys.stderr") as mock_stderr,
            patch("github_monitor.cli._prompts.err"),
            pytest.raises(SystemExit, match="1"),
        ):
            _read_input("prompt: ")
        mock_stderr.write.assert_called_once_with("\n")

    def test_eof_error_prints_error_message(self) -> None:
        with (
            patch("builtins.input", side_effect=EOFError),
            patch("github_monitor.cli._prompts.sys.stderr"),
            patch("github_monitor.cli._prompts.err") as mock_err,
            pytest.raises(SystemExit),
        ):
            _read_input("prompt: ")
        mock_err.assert_called_once()
        assert (
            "non-interactive" in mock_err.call_args[0][0].lower() or "end of input" in mock_err.call_args[0][0].lower()
        )


# ---------------------------------------------------------------------------
# ask_string
# ---------------------------------------------------------------------------


class TestAskString:
    """Tests for ask_string()."""

    def test_returns_user_input(self) -> None:
        with patch("builtins.input", return_value="myvalue"):
            assert ask_string("Name") == "myvalue"

    def test_strips_whitespace(self) -> None:
        with patch("builtins.input", return_value="  spaced  "):
            assert ask_string("Name") == "spaced"

    def test_returns_default_on_empty_input(self) -> None:
        with patch("builtins.input", return_value=""):
            assert ask_string("Name", default="fallback") == "fallback"

    def test_prompt_shows_default(self) -> None:
        mock_input = MagicMock(return_value="")
        with patch("builtins.input", mock_input):
            ask_string("Name", default="val")
        prompt_text = mock_input.call_args[0][0]
        assert "[val]" in prompt_text

    def test_prompt_without_default_has_no_brackets(self) -> None:
        mock_input = MagicMock(return_value="x")
        with patch("builtins.input", mock_input):
            ask_string("Name")
        prompt_text = mock_input.call_args[0][0]
        assert "[" not in prompt_text

    def test_required_loops_on_empty_input(self) -> None:
        mock_input = MagicMock(side_effect=["", "", "finally"])
        with (
            patch("builtins.input", mock_input),
            patch("github_monitor.cli._prompts.warn") as mock_warn,
        ):
            result = ask_string("Name", required=True)
        assert result == "finally"
        assert mock_warn.call_count == 2

    def test_empty_input_no_default_not_required_returns_empty(self) -> None:
        with patch("builtins.input", return_value=""):
            assert ask_string("Name") == ""


# ---------------------------------------------------------------------------
# ask_yes_no
# ---------------------------------------------------------------------------


class TestAskYesNo:
    """Tests for ask_yes_no()."""

    def test_y_returns_true(self) -> None:
        with patch("builtins.input", return_value="y"):
            assert ask_yes_no("Continue?") is True

    def test_yes_returns_true(self) -> None:
        with patch("builtins.input", return_value="yes"):
            assert ask_yes_no("Continue?") is True

    def test_n_returns_false(self) -> None:
        with patch("builtins.input", return_value="n"):
            assert ask_yes_no("Continue?") is False

    def test_no_returns_false(self) -> None:
        with patch("builtins.input", return_value="no"):
            assert ask_yes_no("Continue?") is False

    def test_case_insensitive(self) -> None:
        with patch("builtins.input", return_value="YES"):
            assert ask_yes_no("Continue?") is True

    def test_empty_returns_default_true(self) -> None:
        with patch("builtins.input", return_value=""):
            assert ask_yes_no("Continue?", default=True) is True

    def test_empty_returns_default_false(self) -> None:
        with patch("builtins.input", return_value=""):
            assert ask_yes_no("Continue?", default=False) is False

    def test_prompt_shows_yn_hint_default_true(self) -> None:
        mock_input = MagicMock(return_value="y")
        with patch("builtins.input", mock_input):
            ask_yes_no("Continue?", default=True)
        assert "[Y/n]" in mock_input.call_args[0][0]

    def test_prompt_shows_yn_hint_default_false(self) -> None:
        mock_input = MagicMock(return_value="n")
        with patch("builtins.input", mock_input):
            ask_yes_no("Continue?", default=False)
        assert "[y/N]" in mock_input.call_args[0][0]

    def test_invalid_input_loops_until_valid(self) -> None:
        mock_input = MagicMock(side_effect=["maybe", "dunno", "y"])
        with (
            patch("builtins.input", mock_input),
            patch("github_monitor.cli._prompts.warn") as mock_warn,
        ):
            result = ask_yes_no("Continue?")
        assert result is True
        assert mock_warn.call_count == 2


# ---------------------------------------------------------------------------
# ask_int
# ---------------------------------------------------------------------------


class TestAskInt:
    """Tests for ask_int()."""

    def test_valid_integer_input(self) -> None:
        with patch("builtins.input", return_value="42"):
            assert ask_int("Count", default=10, minimum=1) == 42

    def test_empty_returns_default(self) -> None:
        with patch("builtins.input", return_value=""):
            assert ask_int("Count", default=300, minimum=30) == 300

    def test_prompt_shows_default(self) -> None:
        mock_input = MagicMock(return_value="5")
        with patch("builtins.input", mock_input):
            ask_int("Count", default=10, minimum=1)
        assert "[10]" in mock_input.call_args[0][0]

    def test_non_integer_loops_until_valid(self) -> None:
        mock_input = MagicMock(side_effect=["abc", "12.5", "7"])
        with (
            patch("builtins.input", mock_input),
            patch("github_monitor.cli._prompts.warn") as mock_warn,
        ):
            result = ask_int("Count", default=10, minimum=1)
        assert result == 7
        assert mock_warn.call_count == 2

    def test_below_minimum_loops_until_valid(self) -> None:
        mock_input = MagicMock(side_effect=["5", "29", "30"])
        with (
            patch("builtins.input", mock_input),
            patch("github_monitor.cli._prompts.warn") as mock_warn,
        ):
            result = ask_int("Interval", default=300, minimum=30)
        assert result == 30
        assert mock_warn.call_count == 2
        # Check warning mentions the minimum
        assert "30" in mock_warn.call_args_list[0][0][0]

    def test_minimum_boundary_accepted(self) -> None:
        with patch("builtins.input", return_value="30"):
            assert ask_int("Interval", default=300, minimum=30) == 30


# ---------------------------------------------------------------------------
# ask_list
# ---------------------------------------------------------------------------


class TestAskList:
    """Tests for ask_list()."""

    def test_comma_separated_input(self) -> None:
        with patch("builtins.input", return_value="owner/repo1, org/repo2"):
            result = ask_list("Repos")
        assert result == ["owner/repo1", "org/repo2"]

    def test_strips_whitespace_from_items(self) -> None:
        with patch("builtins.input", return_value="  a , b ,  c  "):
            result = ask_list("Items")
        assert result == ["a", "b", "c"]

    def test_filters_empty_items(self) -> None:
        with patch("builtins.input", return_value="a,,b, ,c"):
            result = ask_list("Items")
        assert result == ["a", "b", "c"]

    def test_empty_input_returns_default(self) -> None:
        with patch("builtins.input", return_value=""):
            result = ask_list("Repos", default=["owner/repo1"])
        assert result == ["owner/repo1"]

    def test_empty_input_no_default_returns_empty_list(self) -> None:
        with patch("builtins.input", return_value=""):
            result = ask_list("Repos")
        assert result == []

    def test_prompt_shows_default_list(self) -> None:
        mock_input = MagicMock(return_value="")
        with patch("builtins.input", mock_input):
            ask_list("Repos", default=["a/b", "c/d"])
        prompt_text = mock_input.call_args[0][0]
        assert "[a/b, c/d]" in prompt_text

    def test_prompt_without_default_has_no_brackets(self) -> None:
        mock_input = MagicMock(return_value="x")
        with patch("builtins.input", mock_input):
            ask_list("Repos")
        prompt_text = mock_input.call_args[0][0]
        assert "[" not in prompt_text

    def test_single_item(self) -> None:
        with patch("builtins.input", return_value="owner/repo"):
            result = ask_list("Repos")
        assert result == ["owner/repo"]
