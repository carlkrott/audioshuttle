"""AudioShuttle CLI entry point."""

from __future__ import annotations

import argparse


def main() -> None:
    """Run AudioShuttle — unified launcher with web UI and tray."""
    parser = argparse.ArgumentParser(
        description="AudioShuttle — AI-agnostic DAW control via MCP"
    )
    parser.add_argument(
        "--transport",
        choices=["standalone", "stdio"],
        default="standalone",
        help="Mode: 'standalone' (web + tray) or 'stdio' (MCP server for external client)",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Host for web UI (default: from config, 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port for web UI (default: from config, 8765)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        default=False,
        help="Don't auto-open browser on startup",
    )
    parser.add_argument(
        "--no-tray",
        action="store_true",
        default=False,
        help="Don't show system tray icon",
    )
    args = parser.parse_args()

    from audioshuttle.config import Settings
    from audioshuttle.launcher import launch

    settings = Settings()
    # stdio mode: never auto-open browser (MCP server is called by another program)
    no_browser = args.no_browser or args.transport == "stdio"
    no_tray = args.no_tray or args.transport == "stdio"

    launch(
        settings,
        transport=args.transport,
        no_browser=no_browser,
        no_tray=no_tray,
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
