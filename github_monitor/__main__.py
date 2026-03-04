"""Allow ``python -m github_monitor`` to launch the daemon.

Builds a unified argument parser that exposes both daemon flags
(``-c``, ``-v``) and management subcommands (``setup``, ``service``,
``uninstall``).  Running ``github-monitor --help`` shows everything.

When no subcommand is given the daemon starts; otherwise the request
is dispatched to the CLI handler via :func:`github_monitor.cli.dispatch`.
"""

from __future__ import annotations

import argparse


def _build_parser() -> argparse.ArgumentParser:
    """Build the unified argument parser.

    Top-level flags (``-c``, ``-v``) are for daemon mode.  Subcommands
    (``setup``, ``service``, ``uninstall``) are for management tasks.
    """
    from .cli import add_subcommands  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        prog="github-monitor",
        description="GitHub PR Monitor",
        epilog="Run without a command to start the daemon.",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=None,
        help="Path to config.toml",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    subparsers = parser.add_subparsers(dest="command")
    add_subcommands(subparsers)

    return parser


def main() -> None:
    """CLI entry point for github-monitor.

    Parses arguments with the unified parser and dispatches to the
    management CLI or starts the daemon.
    """
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is not None:
        from .cli import dispatch  # noqa: PLC0415

        dispatch(args)
        return

    _run_daemon(args)


def _run_daemon(args: argparse.Namespace) -> None:
    """Configure logging from parsed arguments and run the daemon."""
    import asyncio  # noqa: PLC0415
    import logging  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    from .config import load_config  # noqa: PLC0415
    from .daemon import Daemon  # noqa: PLC0415

    config_path = Path(args.config) if args.config else None
    config = load_config(config_path)

    # CLI --verbose overrides config log_level
    log_level = logging.DEBUG if args.verbose else getattr(logging, config.log_level.upper())

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    daemon = Daemon(config, config_path)

    async def run() -> None:
        try:
            await daemon.start()
        finally:
            await daemon.stop()

    asyncio.run(run())


if __name__ == "__main__":
    main()
