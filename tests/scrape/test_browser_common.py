"""CAPTCHA wait limits for browser scraping."""

from __future__ import annotations

from unittest.mock import MagicMock

from agentzero.scrape.browser_common import MAX_HUMAN_PROMPTS, maybe_wait_for_human


def test_maybe_wait_for_human_stops_after_max_attempts(monkeypatch):
    page = MagicMock()
    page.url = "https://www.indeed.com/sorry"
    page.content.return_value = "<html>verify you are human</html>"

    enter_count = 0

    def fake_enter() -> bool:
        nonlocal enter_count
        enter_count += 1
        return enter_count <= MAX_HUMAN_PROMPTS

    monkeypatch.setattr(
        "agentzero.scrape.browser_common._enter_pressed",
        fake_enter,
    )
    monkeypatch.setattr("agentzero.scrape.browser_common.AUTO_VERIFY_WAIT_SEC", 60.0)

    maybe_wait_for_human(
        page,
        site="Indeed",
        html=page.content.return_value,
        needs_human=lambda html, url: "verify you are human" in html,
        input_fn=lambda _: "",
        pause_enabled=True,
        has_results=lambda html: "job_seen_beacon" in html,
        max_attempts=MAX_HUMAN_PROMPTS,
        after_prompt=lambda p: None,
    )

    assert enter_count == MAX_HUMAN_PROMPTS


def test_maybe_wait_for_human_exits_when_jobs_visible():
    page = MagicMock()
    page.url = "https://www.indeed.com/jobs"
    page.content.return_value = "<html>job_seen_beacon</html>"

    maybe_wait_for_human(
        page,
        site="Indeed",
        html=page.content.return_value,
        needs_human=lambda html, url: "verify you are human" in html,
        input_fn=lambda _: "",
        pause_enabled=True,
        has_results=lambda html: "job_seen_beacon" in html,
    )

    page.wait_for_timeout.assert_not_called()


def test_maybe_wait_for_human_reloads_after_prompt(monkeypatch):
    page = MagicMock()
    page.url = "https://www.indeed.com/sorry"
    page.content.return_value = "<html>ray id for this request</html>"
    reloaded: list[str] = []

    def after_prompt(p: object) -> None:
        reloaded.append("yes")
        page.content.return_value = "<html>mosaic-provider-jobcards</html>"

    monkeypatch.setattr("agentzero.scrape.browser_common._enter_pressed", lambda: True)

    maybe_wait_for_human(
        page,
        site="Indeed",
        html=page.content.return_value,
        needs_human=lambda html, url: "ray id" in html.lower(),
        input_fn=lambda _: "",
        pause_enabled=True,
        has_results=lambda html: "mosaic-provider-jobcards" in html,
        max_attempts=1,
        after_prompt=after_prompt,
    )

    assert reloaded == ["yes"]


def test_maybe_wait_for_human_auto_continues_when_jobs_visible(monkeypatch):
    page = MagicMock()
    page.url = "https://www.indeed.com/jobs"
    reads = {"n": 0}

    def content() -> str:
        reads["n"] += 1
        if reads["n"] < 3:
            return "<html>verify you are human</html>"
        return "<html>mosaic-provider-jobcards</html>"

    page.content.side_effect = content
    monkeypatch.setattr("agentzero.scrape.browser_common._enter_pressed", lambda: False)

    maybe_wait_for_human(
        page,
        site="Indeed",
        html="<html>verify you are human</html>",
        needs_human=lambda html, url: "verify" in html,
        input_fn=lambda _: "",
        pause_enabled=True,
        has_results=lambda html: "mosaic-provider-jobcards" in html,
    )

    assert reads["n"] >= 3
