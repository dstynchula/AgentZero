"""Dockerfile layer order and BuildKit cache conventions (P30)."""

from pathlib import Path


def _dockerfile() -> str:
    return Path("Dockerfile").read_text(encoding="utf-8")


def test_dockerfile_enables_buildkit_syntax() -> None:
    text = _dockerfile()
    assert text.startswith("# syntax=docker/dockerfile:1")


def test_dockerfile_pip_cache_mount_before_full_copy() -> None:
    text = _dockerfile()
    assert "mount=type=cache,target=/root/.cache/pip" in text
    assert "PIP_NO_CACHE_DIR" not in text
    pip_idx = text.index("agentzero-build-step: pip")
    playwright_idx = text.index("agentzero-build-step: playwright")
    copy_agentzero_idx = text.index("COPY agentzero ./agentzero")
    assert pip_idx < playwright_idx < copy_agentzero_idx


def test_dockerfile_stub_package_before_pip_install() -> None:
    text = _dockerfile()
    assert "touch agentzero/__init__.py" in text
