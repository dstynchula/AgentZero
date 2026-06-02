"""Launch Google Chrome with remote debugging for Indeed/Glassdoor CDP attach."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_cdp_profile_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / "data" / "browser_profiles" / "cdp"


def find_chrome_executable() -> Path | None:
    """Return Chrome/Chromium binary path for the current OS."""
    if sys.platform == "win32":
        candidates = (
            Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
            / "Google/Chrome/Application/chrome.exe",
        )
        return next((path for path in candidates if path.is_file()), None)
    if sys.platform == "darwin":
        mac = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        if mac.is_file():
            return mac
    for name in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "chrome",
    ):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def launch_cdp_chrome_process(
    *,
    port: int = 9222,
    user_data_dir: Path | None = None,
    quiet: bool = False,
) -> Path:
    """Start Chrome with CDP; returns path to the Chrome executable used."""
    profile = user_data_dir or default_cdp_profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    chrome = find_chrome_executable()
    if chrome is None:
        raise RuntimeError(
            "Google Chrome not found. Install Chrome or set CHROME_EXECUTABLE.\n"
            "Manual launch:\n"
            "  Windows:  .\\scripts\\launch_chrome_cdp.ps1\n"
            "  macOS/Linux: python scripts/launch_chrome_cdp.py"
        )
    subprocess.Popen(  # noqa: S603
        [
            str(chrome),
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    if not quiet:
        _print_launch_hints(port=port, profile_dir=profile)
    return chrome


def _print_launch_hints(*, port: int, profile_dir: Path) -> None:
    print()
    print(f"Starting Chrome with CDP on port {port} ...")
    print(f"Dedicated profile: {profile_dir}")
    print()
    print("Add to .env:")
    print(f"  AGENTZERO_SCRAPE_CDP_URL=http://127.0.0.1:{port}")
    print("  AGENTZERO_SCRAPE_CDP_SITES=indeed,glassdoor")
    print()
    print("Log into Indeed/Glassdoor in that window, then run:")
    print("  python scripts/login_job_boards.py --site indeed,glassdoor")
    print("  python scripts/verify_browser_session.py --site indeed,glassdoor")


def build_launch_commands(*, port: int = 9222) -> list[dict[str, str]]:
    """Platform-labeled copy-paste commands for operators."""
    return [
        {
            "platform": "Windows (PowerShell)",
            "command": f".\\scripts\\launch_chrome_cdp.ps1 -Port {port}",
        },
        {
            "platform": "macOS / Linux",
            "command": f"python scripts/launch_chrome_cdp.py --port {port}",
        },
        {
            "platform": "macOS / Linux (shell)",
            "command": f"./scripts/launch_chrome_cdp.sh --port {port}",
        },
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Start Google Chrome with remote debugging (CDP) on a dedicated profile.",
    )
    parser.add_argument("--port", type=int, default=9222, help="Remote debugging port")
    parser.add_argument(
        "--user-data-dir",
        type=Path,
        default=None,
        help="Chrome profile directory (default: data/browser_profiles/cdp)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Do not print .env hints (for programmatic auto-launch)",
    )
    args = parser.parse_args(argv)
    try:
        launch_cdp_chrome_process(
            port=args.port,
            user_data_dir=args.user_data_dir,
            quiet=args.quiet,
        )
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    if args.quiet:
        print(f"Chrome started (CDP port {args.port}).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
