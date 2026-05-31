"""Scrape tuning: user agents, delays, and site lists."""

from __future__ import annotations

# Modern desktop Chrome on Windows — passed to JobSpy and Playwright.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# JobSpy site names we support (see python-jobspy Site enum).
JOBSPY_SITE_NAMES = frozenset(
    {"indeed", "linkedin", "glassdoor", "zip_recruiter", "google", "bayt", "naukri", "bdjobs"}
)

# Residential IPs get blocked fastest on these boards without proxies.
BLOCKY_JOBSPY_SITES = frozenset({"linkedin", "glassdoor", "zip_recruiter"})

# Core JobSpy boards (Indeed/LinkedIn/Glassdoor use Playwright instead).
DEFAULT_JOBSPY_SITES = ["google", "zip_recruiter"]

# Playwright-backed boards (real browser; best for Indeed).
DEFAULT_BROWSER_SITES = ["indeed", "linkedin", "glassdoor"]
