"""Allow ``python -m forgewatch`` to launch the daemon.

Builds a unified argument parser that exposes both daemon flags
(``-c``, ``-v``) and management subcommands (``setup``, ``service``,
``uninstall``).  Running ``forgewatch --help`` shows everything.

When no subcommand is given the daemon starts; otherwise the request
is dispatched to the CLI handler via :func:`forgewatch.cli.dispatch`.
"""

from __future__ import annotations

import argparse


def build_full_parser() -> argparse.ArgumentParser:
    """Build the unified argument parser.

    Top-level flags (``-c``, ``-v``) are for daemon mode.  Subcommands
    (``setup``, ``service``, ``uninstall``, ``completions``) are for
    management tasks.

    This function is public so that :func:`forgewatch.cli.dispatch` can
    obtain the full parser for shell-completion generation via ``shtab``.
    """
    import shtab  # noqa: PLC0415

    from .cli import add_subcommands  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        prog="forgewatch",
        description="ForgeWatch — GitHub PR Monitor",
        epilog="Run without a command to start the daemon.",
    )
    config_action = parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=None,
        help="Path to config.toml",
    )
    config_action.complete = shtab.FILE  # type: ignore[attr-defined]
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
    """CLI entry point for forgewatch.

    Parses arguments with the unified parser and dispatches to the
    management CLI or starts the daemon.
    """
    parser = build_full_parser()
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
    import sys  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    from .config import CONFIG_DIR, CONFIG_PATH, ConfigError, load_config  # noqa: PLC0415
    from .daemon import Daemon  # noqa: PLC0415

    # Set up basic logging before config load so errors are properly formatted
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger(__name__)

    config_path = Path(args.config) if args.config else None

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        if "not found" in str(exc).lower():
            logger.error(  # noqa: TRY400
                "%s\n\n  To get started, run:   forgewatch setup\n"
                "  Or create config manually:  mkdir -p %s && cp config.example.toml %s",
                exc,
                CONFIG_DIR,
                CONFIG_PATH,
            )
        else:
            logger.error("%s\n\n  Check your config file for errors.", exc)  # noqa: TRY400
        sys.exit(1)

    # CLI --verbose overrides config log_level; reconfigure now that config is loaded
    final_level = logging.DEBUG if args.verbose else getattr(logging, config.log_level.upper())
    logging.getLogger().setLevel(final_level)

    daemon = Daemon(config, config_path)

    async def run() -> None:
        try:
            await daemon.start()
        finally:
            await daemon.stop()

    asyncio.run(run())


if __name__ == "__main__":
    main()
