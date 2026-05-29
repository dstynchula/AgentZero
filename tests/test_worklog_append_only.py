"""Guard that WORKLOG.md is append-only.

The build loop appends entries to WORKLOG.md and must never modify or delete existing lines.
We enforce this by asserting that the version committed at HEAD is an exact prefix of the
current working-tree file (i.e. only net-new trailing content was added).
"""

import pathlib
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKLOG = REPO_ROOT / "WORKLOG.md"


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _git_head_worklog() -> str | None:
    result = subprocess.run(
        ["git", "show", "HEAD:WORKLOG.md"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def test_worklog_exists() -> None:
    assert WORKLOG.is_file(), "WORKLOG.md must exist (the write-only build history)."


def test_worklog_is_append_only() -> None:
    head = _git_head_worklog()
    if head is None:
        pytest.skip("WORKLOG.md not yet committed at HEAD; nothing to compare against.")

    current = _normalize(WORKLOG.read_text(encoding="utf-8"))
    committed = _normalize(head)

    assert current.startswith(committed), (
        "WORKLOG.md is append-only: the committed content must remain an exact prefix of the "
        "current file. Existing lines must not be edited, reordered, or removed."
    )
