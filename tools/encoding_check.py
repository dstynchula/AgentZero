"""Detect UTF-16 text files that should be UTF-8 (CI + fix_encoding)."""

from __future__ import annotations

import pathlib
import sys

TEXT_SUFFIXES = frozenset({".py", ".md", ".toml", ".json", ".example", ".yml", ".yaml", ".txt"})
SKIP_DIRS = frozenset({".venv", ".git", ".pytest_cache", "__pycache__", ".mutmut-cache", "data"})
_SAMPLE_BYTES = 512
_MIN_PAIRS = 2
_PAIR_MATCH_RATIO = 0.8


def utf16_le_pairs(data: bytes) -> int:
    """Count UTF-16LE-like pairs (non-zero low byte, zero high byte) in *data*."""
    even_len = len(data) - (len(data) % 2)
    count = 0
    for i in range(0, even_len, 2):
        if data[i] != 0 and data[i + 1] == 0:
            count += 1
    return count


def utf16_be_pairs(data: bytes) -> int:
    """Count UTF-16BE-like pairs (zero high byte, non-zero low byte) in *data*."""
    even_len = len(data) - (len(data) % 2)
    count = 0
    for i in range(0, even_len, 2):
        if data[i] == 0 and data[i + 1] != 0:
            count += 1
    return count


def looks_utf16(data: bytes) -> bool:
    """Return True when *data* appears to be UTF-16 (LE or BE), with or without BOM."""
    if len(data) < 2:
        return False
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return True

    sample = data[: min(len(data), _SAMPLE_BYTES)]
    pairs = len(sample) // 2
    if pairs < _MIN_PAIRS:
        return False
    threshold = max(_MIN_PAIRS, int(pairs * _PAIR_MATCH_RATIO))
    return utf16_le_pairs(sample) >= threshold or utf16_be_pairs(sample) >= threshold


def decode_utf16(data: bytes) -> str:
    """Decode UTF-16 bytes (any endianness) to str."""
    if data[:2] == b"\xff\xfe":
        return data.decode("utf-16-le")
    if data[:2] == b"\xfe\xff":
        return data.decode("utf-16-be")
    sample = data[: min(len(data), _SAMPLE_BYTES)]
    if utf16_be_pairs(sample) > utf16_le_pairs(sample):
        return data.decode("utf-16-be")
    return data.decode("utf-16-le")


def find_utf16_files(root: pathlib.Path) -> list[pathlib.Path]:
    """Return text files under *root* that look UTF-16 encoded."""
    bad: list[pathlib.Path] = []
    for path in root.rglob("*"):
        if path.is_dir() or any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if data and looks_utf16(data):
            bad.append(path)
    return bad


def main() -> int:
    root = pathlib.Path(".").resolve()
    bad = find_utf16_files(root)
    if bad:
        print("UTF-16 files found:", file=sys.stderr)
        for path in bad:
            print(f"  {path.relative_to(root)}", file=sys.stderr)
        return 1
    print("All checked text files are UTF-8 compatible.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
