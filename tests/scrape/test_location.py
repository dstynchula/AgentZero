
from agentzero.scrape.browser_indeed import build_indeed_search_url
from agentzero.scrape.location import parse_search_location


def test_indeed_browser_remote_usa_url():
    parsed = parse_search_location("remote - usa")
    url = build_indeed_search_url(term="Security Engineer", parsed=parsed)
    assert "l=United+States" in url or "l=United%20States" in url
    assert "remotejob=1" in url
    assert "fromage=" not in url
