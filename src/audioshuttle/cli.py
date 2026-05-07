"""AudioShuttle CLI entry point."""

from __future__ import annotations

import argparse


def main() -> None:
    """Run the AudioShuttle MCP server."""
    parser = argparse.ArgumentParser(
        description="AudioShuttle — AI-agnostic DAW control via MCP"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport mode (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for SSE transport (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port for SSE transport (default: 8765)",
    )
    args = parser.parse_args()

    from audioshuttle.config import Settings
    from audioshuttle.server import create_server

    settings = Settings()
    server = create_server(settings)

    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="sse", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
