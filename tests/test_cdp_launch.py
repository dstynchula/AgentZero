from pathlib import Path
from unittest.mock import patch

from agentzero.scrape.cdp_launch import (
    build_launch_commands,
    default_cdp_profile_dir,
    launch_cdp_chrome_process,
    main,
)


def test_default_cdp_profile_dir():
    root = Path("/repo")
    assert default_cdp_profile_dir(root) == Path("/repo/data/browser_profiles/cdp")


def test_build_launch_commands_three_platforms():
    cmds = build_launch_commands(port=9223)
    assert len(cmds) == 3
    assert "launch_chrome_cdp.ps1" in cmds[0]["command"]
    assert "launch_chrome_cdp.py" in cmds[1]["command"]
    assert "launch_chrome_cdp.sh" in cmds[2]["command"]
    assert "9223" in cmds[0]["command"]


def test_launch_cdp_chrome_process_invokes_chrome(tmp_path: Path):
    chrome = tmp_path / "chrome"
    chrome.write_text("", encoding="utf-8")
    profile = tmp_path / "profile"
    with patch("agentzero.scrape.cdp_launch.find_chrome_executable", return_value=chrome):
        with patch("agentzero.scrape.cdp_launch.subprocess.Popen") as popen:
            launch_cdp_chrome_process(port=9222, user_data_dir=profile, quiet=True)
    popen.assert_called_once()
    args = popen.call_args[0][0]
    assert any("--remote-debugging-port=9222" == a for a in args)
    assert any("user-data-dir" in a and "profile" in a for a in args)


def test_main_returns_1_when_chrome_missing():
    with patch("agentzero.scrape.cdp_launch.find_chrome_executable", return_value=None):
        assert main(["--quiet"]) == 1
