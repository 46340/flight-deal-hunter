"""Parse the result data Google Flights embeds in its page (<script class="ds:1">).

Replaces fast_flights.parser, which (v3.1.0) reads only the "Other flights"
block, crashes on listings marked "Price unavailable", and assumes nothing
follows the JSON. Verified against live pages on 2026-10-03:
  payload[2][0] = "Top flights", payload[3][0] = "Other flights"
  entry[0][1]   = airline names, entry[1][0] = [None, price] or [] if no price
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from selectolax.lexbor import LexborHTMLParser


class ParseError(Exception):
    pass


class GoogleNoFlights(Exception):
    pass


@dataclass
class Offer:
    price: float
    airlines: list[str]
    section: str  # "top" or "other"


SECTIONS = ((2, "top"), (3, "other"))


def extract_payload(html: str):
    script = LexborHTMLParser(html).css_first(r"script.ds\:1")
    if script is None:
        raise ParseError("no ds:1 data script")
    text = script.text()
    start = text.find("data:")
    if start < 0:
        raise ParseError("no data in ds:1 script")
    body = text[start + 5 :].lstrip()
    try:
        payload, end = json.JSONDecoder().raw_decode(body)
    except json.JSONDecodeError as exc:
        raise ParseError(f"bad JSON: {exc}") from None
    if "errorHasStatus: true" in body[end : end + 200]:
        raise GoogleNoFlights("Google returned an error status (no flights)")
    return payload


def parse_offers(html: str) -> list[Offer]:
    """All priced offers on the page, cheapest first. Empty list if the page has none."""
    payload = extract_payload(html)
    if not isinstance(payload, list):
        raise ParseError("payload is not a list")
    offers = []
    for idx, name in SECTIONS:
        try:
            block = payload[idx][0] or []
        except (IndexError, TypeError):
            continue
        for entry in block:
            try:
                price = entry[1][0][1]
                airlines = entry[0][1] or []
            except (IndexError, TypeError):
                continue  # "Price unavailable" and other incomplete listings
            if isinstance(price, (int, float)) and price > 0:
                offers.append(Offer(float(price), [str(a) for a in airlines], name))
    offers.sort(key=lambda o: o.price)
    return offers
