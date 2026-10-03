import pytest

from scraper.blocking import BlockedError
from scraper.providers.google import check_blocked


@pytest.mark.parametrize("status,url,text", [
    (200, "https://consent.google.com/m?continue=https://www.google.com/travel/flights", "<html>"),
    (200, "https://www.google.com/sorry/index?continue=x", "<html>"),
    (429, "https://www.google.com/travel/flights", ""),
    (200, "https://www.google.com/travel/flights", "Our systems have detected unusual traffic from your computer"),
])
def test_block_pages_detected(status, url, text):
    with pytest.raises(BlockedError):
        check_blocked(status, url, text)


def test_normal_page_passes():
    check_blocked(200, "https://www.google.com/travel/flights?tfs=abc", "<script class='ds:1'>")


def test_server_error_is_retryable_not_block():
    with pytest.raises(RuntimeError):
        check_blocked(500, "https://www.google.com/travel/flights", "")
