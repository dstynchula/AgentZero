"""Normalize repository text files to UTF-8 with LF line endings.

This environment's editor writes files as UTF-16; run this before staging so the repo stays
UTF-8. Idempotent: files already UTF-8/LF are left untouched.

Usage:  python tools/fix_encoding.py
"""

from __future__ import annotations

import pathlib
import sys

SKIP_DIRS = {".venv", ".git", ".pytest_cache", "__pycache__", ".mutmut-cache"}


def looks_utf16(data: bytes) -> bool:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return True
    # UTF-16LE without BOM: ASCII text yields a NUL as the second byte.
    return len(data) > 1 and data[0] != 0 and data[1] == 0


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    fixed: list[str] = []
    for path in root.rglob("*"):
        if path.is_dir() or any(part in SKIP_DIRS for part in path.parts):
            continue
        data = path.read_bytes()
        if not data:
            continue
        if looks_utf16(data):
            text = data.decode("utf-16")
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
