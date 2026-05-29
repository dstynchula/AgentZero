"""AgentZero FastMCP server exposing scrape, enrich, rank, and apply tools."""

from __future__ import annotations

import argparse


def build_server():
    try:
        from fastmcp import FastMCP
    except ImportError as exc:
        raise ImportError(
            "MCP server requires fastmcp. Install with: pip install -e '.[mcp]'"
        ) from exc

    from agentzero.config import get_settings
    from agentzero.storage.db import Database

    mcp = FastMCP("AgentZero")
    settings = get_settings()

    @mcp.tool
    def scrape_status() -> dict:
        """Return job counts from the local database."""
        db = Database(settings.db_path)
        try:
            return {"jobs": db.count_jobs()}
        finally:
            db.close()

    @mcp.tool
    def list_quarantine() -> list:
        """List quarantined scrape records."""
        db = Database(settings.db_path)
        try:
            return db.list_quarantine()
        finally:
            db.close()

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentZero MCP server")
    parser.add_argument("--stdio", action="store_true", help="Run MCP over stdio")
    args = parser.parse_args()
    if not args.stdio:
        parser.error("Pass --stdio to run the MCP server (or use --help).")
    server = build_server()
    server.run()


if __name__ == "__main__":
    main()
