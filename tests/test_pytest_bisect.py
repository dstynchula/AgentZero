"""Tests for tools/pytest_bisect.py."""

from __future__ import annotations

from unittest.mock import patch

import tools.pytest_bisect as bisect_mod


def test_bisect_collects_modules(tmp_path):
    stdout = "tests/test_foo.py: 2\ntests/test_bar.py: 1\n"
    with patch.object(bisect_mod.subprocess, "run") as run:
        run.return_value.stdout = stdout
        run.return_value.returncode = 0
        modules = bisect_mod.collect_test_modules(repo_root=tmp_path)
    assert modules == ["tests/test_bar.py", "tests/test_foo.py"]


def test_bisect_records_timeout_as_hang(tmp_path):
    ledger_path = tmp_path / "bisect.json"
    modules = ["tests/test_slow.py"]

    with patch.object(bisect_mod, "run_file", return_value="hang"):
        code = bisect_mod.bisect(
            modules,
            ledger_path=ledger_path,
            repo_root=tmp_path,
            resume=False,
        )
    assert code == 1
    ledger = bisect_mod.load_ledger(ledger_path)
    assert ledger["hang"] == "tests/test_slow.py"
    assert ledger["results"]["tests/test_slow.py"] == "hang"


def test_run_file_ok_on_zero_exit(tmp_path):
    with patch.object(bisect_mod.subprocess, "run") as run:
        run.return_value.returncode = 0
        assert bisect_mod.run_file("tests/test_x.py", repo_root=tmp_path) == "ok"


def test_dry_run_lists_modules(capsys, tmp_path):
    modules = ["tests/a.py", "tests/b.py"]
    code = bisect_mod.bisect(modules, ledger_path=tmp_path / "l.json", dry_run=True)
    assert code == 0
    out = capsys.readouterr()
    assert "tests/a.py" in out.out
    assert "tests/b.py" in out.out
