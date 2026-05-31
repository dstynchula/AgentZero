"""CLI progress helper."""

from __future__ import annotations

from agentzero.loops.progress import Progress


def test_progress_step_increments(capsys):
    p = Progress(2, label="Rank")
    p.announce()
    p.step("job one")
    p.step("job two")
    p.finish("ok")
    out = capsys.readouterr().out
    assert "Rank [1/2] job one" in out
    assert "Rank [2/2] job two" in out
    assert "done 2/2" in out
