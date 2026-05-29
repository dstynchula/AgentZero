import subprocess
import sys


def test_mcp_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "agentzero.mcp_server", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "AgentZero MCP server" in result.stdout
