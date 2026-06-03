"""Run CodeQL locally with the same Python security suite as GitHub Advanced Security."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CODEQL_DIR = REPO_ROOT / ".codeql"
DB_DIR = CODEQL_DIR / "db"
SARIF_PATH = CODEQL_DIR / "results.sarif"

# Matches GitHub Code scanning defaults for Python on this repo.
QUERY_SUITE = "codeql/python-queries:codeql-suites/python-security-extended.qls"

# Same roots as CI ruff; CodeQL still scans imports across the tree.
SCAN_PREFIXES = ("agentzero/", "tests/", "scripts/", "tools/")

INSTALL_HINT = """\
CodeQL CLI is required for the pre-push hook (blocks the same alerts as GitHub PR checks).

Install (one-time):
  1. Download the latest codeql-win64.zip from:
     https://github.com/github/codeql-cli-binaries/releases
  2. Extract and add the folder containing codeql.exe to PATH
     (or set CODEQL_CLI=C:\\path\\to\\codeql.exe)

Then re-run: pre-commit run codeql --hook-stage pre-push

Emergency skip (not for normal use): set AGENTZERO_SKIP_CODEQL=1
"""


def resolve_codeql() -> str | None:
    env_cli = os.environ.get("CODEQL_CLI", "").strip()
    if env_cli:
        path = Path(env_cli)
        if path.is_file():
            return str(path)
    return shutil.which("codeql")


def _run(cmd: list[str], *, label: str) -> None:
    print(f"codeql_check: {label}…", flush=True)
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)


def _normalize_relpath(uri: str) -> str | None:
    raw = uri.removeprefix("file://")
    if len(raw) > 2 and raw[0] == "/" and raw[2] == ":":
        raw = raw[1:]
    path = Path(raw)
    try:
        if path.is_absolute():
            return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
        return path.as_posix().replace("\\", "/")
    except ValueError:
        return None


def _in_scan_roots(uri: str) -> bool:
    rel = _normalize_relpath(uri)
    if rel is None:
        return False
    return rel.startswith(SCAN_PREFIXES)


def _collect_findings() -> list[str]:
    data = json.loads(SARIF_PATH.read_text(encoding="utf-8"))
    lines: list[str] = []
    for run in data.get("runs", []):
        rules = {rule["id"]: rule for rule in run.get("tool", {}).get("driver", {}).get("rules", [])}
        for result in run.get("results", []):
            level = (result.get("level") or "warning").lower()
            if level not in {"error", "warning", "note"}:
                continue
            locations = result.get("locations") or []
            if not locations:
                continue
            physical = locations[0].get("physicalLocation", {})
            artifact = physical.get("artifactLocation", {})
            uri = artifact.get("uri") or ""
            if not _in_scan_roots(uri):
                continue
            region = physical.get("region", {})
            line = region.get("startLine", "?")
            rule_id = result.get("ruleId", "unknown")
            rule = rules.get(rule_id, {})
            title = rule.get("shortDescription", {}).get("text") or rule_id
            rel = _normalize_relpath(uri) or uri
            message = (result.get("message") or {}).get("text") or title
            lines.append(f"  [{level}] {rel}:{line} — {title}: {message.splitlines()[0]}")
    return lines


def main() -> int:
    if os.environ.get("AGENTZERO_SKIP_CODEQL") == "1":
        print("AGENTZERO_SKIP_CODEQL=1 — skipping CodeQL.")
        return 0

    codeql = resolve_codeql()
    if not codeql:
        print(INSTALL_HINT, file=sys.stderr)
        return 1

    CODEQL_DIR.mkdir(parents=True, exist_ok=True)

    try:
        _run(
            [
                codeql,
                "database",
                "create",
                str(DB_DIR),
                "--language=python",
                f"--source-root={REPO_ROOT}",
                "--overwrite",
            ],
            label="creating database",
        )
        _run(
            [
                codeql,
                "database",
                "analyze",
                str(DB_DIR),
                "--format=sarif-latest",
                f"--output={SARIF_PATH}",
                "--download",
                QUERY_SUITE,
            ],
            label="analyzing (python-security-extended)",
        )
    except subprocess.CalledProcessError as exc:
        print(f"codeql_check: CodeQL failed (exit {exc.returncode}).", file=sys.stderr)
        return exc.returncode or 1

    findings = _collect_findings()
    if not findings:
        print("codeql_check: no findings in agentzero/, tests/, scripts/, or tools/.")
        return 0

    print("codeql_check: findings (fix before push — same class as GitHub CodeQL PR check):", file=sys.stderr)
    for line in findings:
        print(line, file=sys.stderr)
    print(f"\n{len(findings)} finding(s). See {SARIF_PATH} for details.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
