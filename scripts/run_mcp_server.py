#!/usr/bin/env python3
"""Launch AgentZero MCP server using the repo venv when available."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _venv_python(repo: Path) -> Path | None:
    if sys.platform == "win32":
        candidate = repo / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = repo / ".venv" / "bin" / "python"
    return candidate if candidate.is_file() else None


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    venv_py = _venv_python(repo)
    if venv_py is not None and Path(sys.executable).resolve() != venv_py.resolve():
        os.chdir(repo)
        os.execv(str(venv_py), [str(venv_py), "-m", "agentzero.mcp_server", *sys.argv[1:]])
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from agentzero.mcp_server import main as mcp_main

    mcp_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
