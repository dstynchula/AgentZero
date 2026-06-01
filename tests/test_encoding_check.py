"""Tests for UTF-16 detection (LE and BE)."""

from tools.encoding_check import looks_utf16, utf16_be_pairs, utf16_le_pairs


def test_utf16_le_bom():
    assert looks_utf16(b"\xff\xfe#\x00")


def test_utf16_be_bom():
    assert looks_utf16(b"\xfe\xff\x00#")


def test_utf16_le_without_bom():
    assert looks_utf16(b"#\x00 \x00#\x00\n\x00")


def test_utf16_be_without_bom():
    # ASCII in UTF-16BE: null in first byte of each pair — missed by old CI check.
    assert looks_utf16(b"\x00#\x00 \x00#\x00\n")


def test_utf8_ascii_not_flagged():
    assert not looks_utf16(b"#!/usr/bin/env python3\nprint('hi')\n")


def test_utf8_multibyte_not_flagged():
    assert not looks_utf16("café\n".encode())


def test_pair_counters():
    le = b"a\x00b\x00"
    be = b"\x00a\x00b"
    assert utf16_le_pairs(le) == 2
    assert utf16_be_pairs(le) == 0
    assert utf16_be_pairs(be) == 2
    assert utf16_le_pairs(be) == 0
