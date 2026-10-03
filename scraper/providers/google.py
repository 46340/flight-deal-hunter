"""Google Flights: queries and links built with fast-flights v3.1.0, parsing in google_parse.

fast_flights.get_flights() does not look at the HTTP response, so a consent or
captcha page crashes it. We fetch with the same client settings ourselves,
check for blocking, then parse with our own parser (see google_parse.py).

Multi-city searches are not supported: Google loads their results after the
page opens, so the downloaded HTML has none.
"""

from __future__ import annotations

import os

from ..blocking import BlockedError
from ..models import Fare, LegKey
from .base import EmptyResponse, NoFlights, Provider
from .google_parse import GoogleNoFlights, ParseError, parse_offers

URL = "https://www.google.com/travel/flights"

# Google's "Reject all" cookie choice. Only needed from EU IPs (e.g. local runs
# from Denmark); GitHub's runners are not shown the consent page.
EU_CONSENT_COOKIE = "SOCS=CAI"

BLOCK_MARKERS = (
    "Our systems have detected unusual traffic",
    'id="captcha-form"',
    "g-recaptcha",
)


def check_blocked(status: int, final_url: str, text: str) -> None:
    """Raise BlockedError for consent walls, captchas and rate limiting."""
    if status == 429:
        raise BlockedError("HTTP 429 rate limited")
    if "consent.google." in final_url:
        raise BlockedError("cookie consent page (set FDH_EU_CONSENT=1 when running from the EU)")
    if "/sorry/" in final_url:
        raise BlockedError("captcha page (/sorry/)")
    for marker in BLOCK_MARKERS:
        if marker in text:
            raise BlockedError(f"captcha page ({marker!r})")
    if status >= 400:
        raise RuntimeError(f"HTTP {status}")


class GoogleFlightsProvider(Provider):
    name = "google"

    def __init__(self, language: str = "en-US", client=None, proxy: str | None = None,
                 eu_consent: bool | None = None):
        self.language = language
        if eu_consent is None:
            eu_consent = os.environ.get("FDH_EU_CONSENT", "") == "1"
        self.headers = {"Cookie": EU_CONSENT_COOKIE} if eu_consent else {}
        if client is None:
            from primp import Client

            client = Client(
                impersonate="chrome_145",
                impersonate_os="macos",
                referer=True,
                cookie_store=True,
                proxy=proxy,
                timeout=45,
            )
        self.client = client

    def build_query(self, legs: tuple[LegKey, ...], trip: str, single_ticket_only: bool = False):
        from fast_flights import FlightQuery, Passengers, create_query

        return create_query(
            flights=[FlightQuery(date=leg.date.isoformat(), from_airport=leg.origin, to_airport=leg.destination) for leg in legs],
            trip=trip,
            seat="economy",
            passengers=Passengers(adults=1),
            currency=legs[0].currency,
            language=self.language,
            max_stops=None,
            hide_separate_and_self_transfer=single_ticket_only,
        )

    def fetch(self, query) -> str:
        resp = self.client.get(URL, params=query.params(), headers=self.headers)
        text = resp.text
        check_blocked(resp.status_code, str(resp.url), text)
        return text

    def _search(self, legs: tuple[LegKey, ...], trip: str, single_ticket_only: bool) -> Fare:
        query = self.build_query(legs, trip, single_ticket_only)
        html = self.fetch(query)
        try:
            offers = parse_offers(html)
        except GoogleNoFlights:
            raise NoFlights(trip) from None
        except ParseError as exc:
            raise EmptyResponse(f"unparseable: {exc}") from None
        if not offers:
            raise EmptyResponse("no priced results")
        best = offers[0]
        return Fare(price=best.price, currency=legs[0].currency, airlines=best.airlines, url=query.url())

    def one_way(self, leg: LegKey) -> Fare:
        return self._search((leg,), "one-way", single_ticket_only=False)

    def itinerary(self, legs: tuple[LegKey, ...], kind: str) -> Fare:
        if kind != "round-trip":
            raise ValueError(f"Google provider only re-prices round-trips, not {kind}")
        # Hide Google's own self-transfer combos so "single ticket" really is one ticket.
        return self._search(legs, kind, single_ticket_only=True)
