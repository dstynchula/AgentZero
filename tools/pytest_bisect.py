"""File-level pytest bisect with subprocess timeout (find hanging test modules)."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = REPO_ROOT / "data" / "pytest-bisect.json"
MODULE_LINE = re.compile(r"^(tests/\S+\.py):\s+\d+\s*$")
PER_FILE_TIMEOUT_SEC = 45


def collect_test_modules(*, repo_root: Path = REPO_ROOT) -> list[str]:
    """Return sorted test module paths from ``pytest --collect-only -q``."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    modules: list[str] = []
    seen: set[str] = set()
    for line in result.stdout.splitlines():
        match = MODULE_LINE.match(line.strip().replace("\\", "/"))
        if not match:
            continue
        path = match.group(1)
        if path not in seen:
            seen.add(path)
            modules.append(path)
    return sorted(modules)


def load_ledger(path: Path) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"results": {}, "hang": None}


def save_ledger(path: Path, ledger: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")


def run_file(
    module: str,
    *,
    repo_root: Path = REPO_ROOT,
    timeout_sec: int = PER_FILE_TIMEOUT_SEC,
) -> str:
    """Run one test file; return ``ok``, ``fail``, or ``hang``."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", module, "-q", "--no-cov"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        return "hang"
    return "ok" if proc.returncode == 0 else "fail"


def bisect(
    modules: list[str],
    *,
    ledger_path: Path = DEFAULT_LEDGER,
    repo_root: Path = REPO_ROOT,
    timeout_sec: int = PER_FILE_TIMEOUT_SEC,
    dry_run: bool = False,
    resume: bool = True,
) -> int:
    ledger = load_ledger(ledger_path) if resume else {"results": {}, "hang": None}
    results: dict[str, str] = dict(ledger.get("results") or {})

    for module in modules:
        if module in results:
            continue
        if dry_run:
            print(module)
            continue
        status = run_file(module, repo_root=repo_root, timeout_sec=timeout_sec)
        results[module] = status
        ledger["results"] = results
        save_ledger(ledger_path, ledger)
        print(f"{status:4}  {module}", flush=True)
        if status == "hang":
            ledger["hang"] = module
            save_ledger(ledger_path, ledger)
            print(f"pytest_bisect: hang detected in {module}", file=sys.stderr)
            return 1

    if dry_run:
        print(f"pytest_bisect: {len(modules)} module(s)", file=sys.stderr)
        return 0

    failed = [m for m, s in results.items() if s == "fail"]
    if failed:
        print(f"pytest_bisect: {len(failed)} module(s) failed", file=sys.stderr)
        return 1
    print("pytest_bisect: all modules ok", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bisect pytest hangs by test file.")
    parser.add_argument("--dry-run", action="store_true", help="List modules only.")
    parser.add_argument("--no-resume", action="store_true", help="Ignore prior ledger.")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--timeout", type=int, default=PER_FILE_TIMEOUT_SEC)
    args = parser.parse_args(argv)

    modules = collect_test_modules()
    return bisect(
        modules,
        ledger_path=args.ledger,
        timeout_sec=args.timeout,
        dry_run=args.dry_run,
        resume=not args.no_resume,
    )


if __name__ == "__main__":
    raise SystemExit(main())
