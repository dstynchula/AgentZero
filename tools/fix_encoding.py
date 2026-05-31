"""Normalize repository text files to UTF-8 with LF line endings.

Prefer preventing UTF-16 on Windows by setting PowerShell defaults (see README):

    $PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
    $PSDefaultParameterValues['Set-Content:Encoding'] = 'utf8'

Or:  . .\\scripts\\dev-env.ps1

Run this script before ``git add`` if anything still lands as UTF-16. Idempotent: files
already UTF-8/LF are left untouched.

Usage:  python tools/fix_encoding.py
"""

from __future__ import annotations

import pathlib
import sys

SKIP_DIRS = {".venv", ".git", ".pytest_cache", "__pycache__", ".mutmut-cache", "data"}


def looks_utf16(data: bytes) -> bool:
    from tools.encoding_check import looks_utf16 as _looks_utf16

    return _looks_utf16(data)


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    fixed: list[str] = []
    for path in root.rglob("*"):
        if path.is_dir() or any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if not data:
            continue
        if looks_utf16(data):
            from tools.encoding_check import decode_utf16

            text = decode_utf16(data)
            path.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))
            fixed.append(str(path.relative_to(root)))
    if fixed:
        print(f"Re-encoded {len(fixed)} file(s) to UTF-8:")
        for f in fixed:
            print(f"  {f}")
    else:
        print("All files already UTF-8.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
