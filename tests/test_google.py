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


# Parser tests against real pages saved by scripts/probe_google.py on 2026-10-03.
from pathlib import Path  # noqa: E402

from scraper.providers.google_parse import GoogleNoFlights, ParseError, parse_offers  # noqa: E402

PAGES = Path(__file__).parent / "fixtures" / "google"


def page(name):
    return (PAGES / name).read_text(encoding="utf-8")


def test_reads_top_flights_block_that_fast_flights_skips():
    offers = parse_offers(page("one_way_iad_ham.html"))
    assert offers[0].price == 2187 and offers[0].section == "top"
    assert offers[0].airlines == ["Tap Air Portugal"]
    assert [o.price for o in offers] == sorted(o.price for o in offers)


def test_skips_price_unavailable_listings():
    offers = parse_offers(page("one_way_cph_lhr.html"))
    assert offers[0].price == 871
    assert len(offers) == 10  # 4 top + 11 other, minus 5 without a price


def test_round_trip_total_matches_browser():
    # Chrome showed "DKK 3,438 round trip" style totals; CPH-JFK Nov 4 to 10
    assert parse_offers(page("round_trip_cph_jfk.html"))[0].price == 3438


def test_multi_city_page_has_no_results():
    assert parse_offers(page("multi_city_empty.html")) == []


def test_trailing_content_after_json():
    html = """<script class="ds:1">AF_initDataCallback({key: 'ds:1', hash: '1', data:[null,null,
    [[[[1,["SAS"]],[[null,999],"x"]]]],null], sideChannel: {}, other: [1,2]});</script>"""
    (o,) = parse_offers(html)
    assert (o.price, o.airlines, o.section) == (999, ["SAS"], "top")


def test_error_status_means_no_flights():
    html = """<script class="ds:1">AF_initDataCallback({key: 'ds:1', data:[null], errorHasStatus: true});</script>"""
    with pytest.raises(GoogleNoFlights):
        parse_offers(html)


@pytest.mark.parametrize("html", ["<html></html>", '<script class="ds:1">nothing here</script>',
                                  '<script class="ds:1">x({data:[1,2</script>'])
def test_unparseable_pages(html):
    with pytest.raises(ParseError):
        parse_offers(html)


class FakeResp:
    def __init__(self, text, status=200, url="https://www.google.com/travel/flights?tfs=x"):
        self.text, self.status_code, self.url = text, status, url


class FakeClient:
    def __init__(self, resp):
        self.resp, self.calls = resp, []

    def get(self, url, params=None, headers=None):
        self.calls.append((params, headers))
        return self.resp


def _leg(o, d, day):
    from datetime import date
    from scraper.models import LegKey
    return LegKey(o, d, date(2026, 11, day), "DKK")


def test_provider_one_way_and_round_trip_flags():
    from scraper.providers.google import GoogleFlightsProvider

    g = GoogleFlightsProvider(client=FakeClient(FakeResp(page("round_trip_cph_jfk.html"))), eu_consent=False)
    fare = g.itinerary((_leg("CPH", "JFK", 4), _leg("JFK", "CPH", 10)), "round-trip")
    assert fare.price == 3438 and fare.url.startswith("https://www.google.com/travel/flights/search?tfs=")
    rt_tfs = g.client.calls[-1][0]["tfs"]
    g.one_way(_leg("CPH", "JFK", 4))
    assert g.client.calls[-1][1] == {}
    # the single-ticket-only flag changes the encoded query
    plain = g.build_query((_leg("CPH", "JFK", 4), _leg("JFK", "CPH", 10)), "round-trip").params()["tfs"]
    assert plain != rt_tfs
    with pytest.raises(ValueError):
        g.itinerary((_leg("CPH", "JFK", 4), _leg("IAD", "HAM", 10)), "multi-city")


def test_provider_maps_outcomes():
    from scraper.providers.base import EmptyResponse
    from scraper.providers.google import GoogleFlightsProvider

    g = GoogleFlightsProvider(client=FakeClient(FakeResp(page("multi_city_empty.html"))))
    with pytest.raises(EmptyResponse):
        g.one_way(_leg("CPH", "JFK", 4))
    g = GoogleFlightsProvider(client=FakeClient(FakeResp("x", url="https://consent.google.com/m?x")))
    with pytest.raises(BlockedError):
        g.one_way(_leg("CPH", "JFK", 4))


def test_eu_consent_cookie_sent_when_enabled(monkeypatch):
    from scraper.providers.google import GoogleFlightsProvider

    monkeypatch.setenv("FDH_EU_CONSENT", "1")
    g = GoogleFlightsProvider(client=FakeClient(FakeResp(page("one_way_cph_lhr.html"))))
    g.one_way(_leg("CPH", "LHR", 4))
    assert g.client.calls[-1][1] == {"Cookie": "SOCS=CAI"}
