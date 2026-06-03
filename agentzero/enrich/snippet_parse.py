"""Parse company size and Glassdoor signals from search snippets and page text."""

from __future__ import annotations

import re

from agentzero.enrich.comp import parse_employee_count
from agentzero.enrich.company import bucket_employee_count

# "1,001-5,000 employees", "201 to 500 employees", "Company size · 51-200"
SIZE_RANGE_RE = re.compile(
    r"(?:company\s+size\s*[:·•]\s*)?"
    r"(?P<lo>[\d,]+)\s*(?:-|–|to)\s*(?P<hi>[\d,]+)\+?\s*employees?",
    re.IGNORECASE,
)

# Pre-bucketed ranges copied from LinkedIn / Google knowledge panels
SIZE_BUCKET_LABEL_RE = re.compile(
    r"(?P<label>\d[\d,]*\s*[-–]\s*\d[\d,]*\+?)\s*employees?",
    re.IGNORECASE,
)

GLASSDOOR_RATING_RE = re.compile(
    r"(?:glassdoor|rating)[^.\n]{0,60}?(?P<rating>\d\.\d)",
    re.IGNORECASE,
)

GLASSDOOR_INLINE_RE = re.compile(
    r"(?P<rating>\d\.\d)\s*(?:★|stars?)?\s*(?:[·|•]\s*)?(?P<reviews>[\d,]+)?\s*reviews?",
    re.IGNORECASE,
)

GLASSDOOR_OUT_OF_FIVE_RE = re.compile(
    r"(?P<rating>\d\.\d)\s+out\s+of\s+5",
    re.IGNORECASE,
)

REVIEWS_ONLY_RE = re.compile(
    r"(?P<reviews>[\d,]+)\s+(?:\w+\s+){0,4}reviews?\b",
    re.IGNORECASE,
)

LINKEDIN_EMPLOYEES_RE = re.compile(
    r"(?P<count>[\d,]+)\+?\s*employees\s+(?:on\s+)?linkedin",
    re.IGNORECASE,
)

EXCHANGE_TICKER_RE = re.compile(
    r"\b(?:NASDAQ|NYSE|AMEX|NYSEARCA)\s*:\s*(?P<ticker>[A-Z]{1,5})\b"
)

PUBLIC_COMPANY_RE = re.compile(
    r"publicly\s+traded|public\s+company|listed\s+on\s+(?:the\s+)?(?:nasdaq|nyse|amex)",
    re.IGNORECASE,
)

PRIVATE_COMPANY_RE = re.compile(
    r"privately\s+held|private\s+company|not\s+publicly\s+traded|venture[- ]backed\s+startup",
    re.IGNORECASE,
)


def _parse_int(raw: str) -> int | None:
    cleaned = raw.replace(",", "").strip()
    if not cleaned.isdigit():
        return None
    return int(cleaned)


def normalize_size_label(label: str) -> str:
    """Normalize '1,001 - 5,000+' to '1001-5000'."""
    parts = re.split(r"\s*[-–]\s*", label.strip())
    nums = [_parse_int(p.rstrip("+")) for p in parts]
    if len(nums) == 2 and nums[0] is not None and nums[1] is not None:
        return f"{nums[0]}-{nums[1]}"
    return re.sub(r"\s+", "", label.replace(",", ""))


def parse_company_size_from_text(text: str) -> str | None:
    """Extract a company-size bucket or range label from free text."""
    if not text.strip():
        return None

    match = SIZE_RANGE_RE.search(text)
    if match:
        lo = _parse_int(match.group("lo"))
        hi = _parse_int(match.group("hi"))
        if lo is not None and hi is not None:
            return bucket_employee_count((lo + hi) // 2)

    bucket = SIZE_BUCKET_LABEL_RE.search(text)
    if bucket:
        return normalize_size_label(bucket.group("label"))

    linkedin = LINKEDIN_EMPLOYEES_RE.search(text)
    if linkedin:
        count = _parse_int(linkedin.group("count"))
        if count is not None:
            return bucket_employee_count(count)

    count = parse_employee_count(text)
    if count is not None:
        return bucket_employee_count(count)
    return None


def parse_glassdoor_from_text(text: str) -> tuple[float | None, int | None]:
    """Parse Glassdoor-style rating and review count from a snippet or page."""
    if not text.strip():
        return None, None

    lowered = text.lower()
    rating: float | None = None
    reviews: int | None = None

    if "glassdoor" in lowered:
        match = GLASSDOOR_RATING_RE.search(text)
        if match:
            rating = float(match.group("rating"))

    inline = GLASSDOOR_INLINE_RE.search(text)
    if inline and ("glassdoor" in lowered or "review" in lowered):
        rating = rating or float(inline.group("rating"))
        raw_reviews = inline.group("reviews")
        if raw_reviews:
            reviews = _parse_int(raw_reviews)

    out_of_five = GLASSDOOR_OUT_OF_FIVE_RE.search(text)
    if out_of_five and "glassdoor" in lowered:
        rating = rating or float(out_of_five.group("rating"))

    if reviews is None and ("glassdoor" in lowered or "review" in lowered):
        rev = REVIEWS_ONLY_RE.search(text)
        if rev:
            reviews = _parse_int(rev.group("reviews"))

    if rating is not None and not 0.0 <= rating <= 5.0:
        return None, reviews
    return rating, reviews


def parse_public_company_from_text(text: str) -> tuple[bool | None, str | None]:
    """Return (is_public_company, stock_ticker) from search snippets; None when unknown."""
    if not text.strip():
        return None, None
    if PRIVATE_COMPANY_RE.search(text):
        return False, None
    match = EXCHANGE_TICKER_RE.search(text)
    if match:
        return True, match.group("ticker")
    if PUBLIC_COMPANY_RE.search(text):
        return True, None
    return None, None
