"""CLI subcommand parser and dispatch for forgewatch management commands."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import _SubParsersAction


def add_subcommands(subparsers: _SubParsersAction[argparse.ArgumentParser]) -> None:
    """Add CLI management subcommands to an existing subparsers group.

    This allows the main entry point to build a unified parser that
    includes both daemon flags and management subcommands.

    Parameters
    ----------
    subparsers:
        A subparsers action (from ``parser.add_subparsers()``) to which
        ``setup``, ``service``, ``uninstall``, and ``completions``
        subcommands are added.
    """
    # setup
    setup_parser = subparsers.add_parser("setup", help="Initial setup wizard")
    setup_group = setup_parser.add_mutually_exclusive_group()
    setup_group.add_argument(
        "--config-only",
        action="store_true",
        help="Only create config file, skip service installation",
    )
    setup_group.add_argument(
        "--service-only",
        action="store_true",
        help="Only install systemd services, skip config wizard",
    )

    # service
    service_parser = subparsers.add_parser("service", help="Manage systemd services")
    service_parser.add_argument(
        "action",
        choices=["install", "start", "stop", "restart", "status", "enable", "disable"],
        help="Service action to perform",
    )

    # uninstall
    subparsers.add_parser("uninstall", help="Remove services and optionally config")

    # completions
    comp = subparsers.add_parser("completions", help="Generate shell completions")
    comp.add_argument(
        "shell",
        choices=["bash", "zsh", "tcsh"],
        help="Shell to generate completions for",
    )


def dispatch(args: argparse.Namespace) -> None:
    """Dispatch to the appropriate CLI subcommand handler.

    Parameters
    ----------
    args:
        Pre-parsed argument namespace with a ``command`` attribute
        identifying the subcommand.
    """
    if args.command == "setup":
        from forgewatch.cli.setup import run_setup  # noqa: PLC0415

        run_setup(config_only=args.config_only, service_only=args.service_only)

    elif args.command == "service":
        from forgewatch.cli.service import run_service  # noqa: PLC0415

        run_service(action=args.action)

    elif args.command == "uninstall":
        from forgewatch.cli.uninstall import run_uninstall  # noqa: PLC0415

        run_uninstall()

    elif args.command == "completions":
        import shtab  # noqa: PLC0415

        from forgewatch.__main__ import build_full_parser  # noqa: PLC0415

        parser = build_full_parser()
        print(shtab.complete(parser, args.shell))  # noqa: T201


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for CLI management subcommands.

    Returns an ``ArgumentParser`` with ``setup``, ``service``,
    ``uninstall``, and ``completions`` subcommands.  This is used by
    :func:`run_cli` and by tests that need to inspect the parser
    structure independently.
    """
    parser = argparse.ArgumentParser(
        prog="forgewatch",
        description="ForgeWatch — GitHub PR Monitor",
    )
    subparsers = parser.add_subparsers(dest="command")
    add_subcommands(subparsers)
    return parser


def run_cli(argv: list[str] | None = None) -> None:
    """Parse arguments and dispatch to the appropriate subcommand.

    Parameters
    ----------
    argv:
        Command-line arguments to parse.  Defaults to ``sys.argv[1:]``.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    dispatch(args)
