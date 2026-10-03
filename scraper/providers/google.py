"""Google Flights via fast-flights v3.1.0.

fast_flights.get_flights() does not look at the HTTP response, so a consent or
captcha page crashes its parser. We fetch with the same client settings
ourselves, check for blocking, then hand the HTML to fast_flights' parser.
"""

from __future__ import annotations

from ..blocking import BlockedError
from ..models import Fare, LegKey
from .base import EmptyResponse, NoFlights, Provider

URL = "https://www.google.com/travel/flights"

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
        raise BlockedError("cookie consent page")
    if "/sorry/" in final_url:
        raise BlockedError("captcha page (/sorry/)")
    for marker in BLOCK_MARKERS:
        if marker in text:
            raise BlockedError(f"captcha page ({marker!r})")
    if status >= 400:
        raise RuntimeError(f"HTTP {status}")


class GoogleFlightsProvider(Provider):
    name = "google"

    def __init__(self, language: str = "en-US", client=None, proxy: str | None = None):
        self.language = language
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

    def build_query(self, legs: tuple[LegKey, ...], trip: str):
        from fast_flights import FlightQuery, Passengers, create_query

        return create_query(
            flights=[FlightQuery(date=leg.date.isoformat(), from_airport=leg.origin, to_airport=leg.destination) for leg in legs],
            trip=trip,
            seat="economy",
            passengers=Passengers(adults=1),
            currency=legs[0].currency,
            language=self.language,
            max_stops=None,
        )

    def _search(self, legs: tuple[LegKey, ...], trip: str) -> Fare:
        from fast_flights import FlightsNotFound
        from fast_flights.parser import parse

        query = self.build_query(legs, trip)
        resp = self.client.get(URL, params=query.params())
        text = resp.text
        check_blocked(resp.status_code, str(resp.url), text)
        try:
            results = parse(text)
        except FlightsNotFound:
            raise NoFlights(trip) from None
        except Exception as exc:  # page without the data script, or a changed layout
            raise EmptyResponse(f"unparseable: {type(exc).__name__}") from None
        priced = [f for f in results if isinstance(f.price, (int, float)) and f.price > 0]
        if not priced:
            raise EmptyResponse("no priced results")
        best = min(priced, key=lambda f: f.price)
        return Fare(price=float(best.price), currency=legs[0].currency, airlines=list(best.airlines), url=query.url())

    def one_way(self, leg: LegKey) -> Fare:
        return self._search((leg,), "one-way")

    def itinerary(self, legs: tuple[LegKey, ...], kind: str) -> Fare:
        if kind not in ("round-trip", "multi-city"):
            raise ValueError(kind)
        return self._search(legs, kind)
