"""Live check of Google Flights through fast-flights (a handful of polite queries).

Answers two questions:
1. Are we blocked from this machine (consent page, captcha)?
2. Is the round-trip / multi-city price the whole-itinerary total? Compare it with
   the one-way prices of the same legs and with what query.url() shows in a browser.

Usage: python scripts/probe_google.py [--out-date 2026-11-04] [--ret-date 2026-11-10]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.blocking import BlockedError  # noqa: E402
from scraper.models import LegKey  # noqa: E402
from scraper.providers.google import URL, GoogleFlightsProvider, check_blocked  # noqa: E402


def raw_sections(text: str) -> dict:
    """Min prices in the two result blocks of Google's embedded data (fast-flights reads only [3])."""
    from selectolax.lexbor import LexborHTMLParser

    script = LexborHTMLParser(text).css_first(r"script.ds\:1")
    if script is None:
        return {"error": "no ds:1 script"}
    data = script.text().split("data:", 1)[1].rsplit(",", 1)[0]
    payload = json.loads(data)
    out = {}
    for idx in (2, 3):
        try:
            block = payload[idx][0] or []
            prices = sorted(k[1][0][1] for k in block if k[1] and k[1][0] and k[1][0][1])
            out[f"payload[{idx}]"] = {"count": len(block), "cheapest": prices[:3]}
        except (IndexError, TypeError) as exc:
            out[f"payload[{idx}]"] = {"error": repr(exc)}
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out-date", type=date.fromisoformat, default=date.today() + timedelta(days=32))
    p.add_argument("--ret-date", type=date.fromisoformat)
    p.add_argument("--currency", default="DKK")
    a = p.parse_args()
    out_d = a.out_date
    ret_d = a.ret_date or out_d + timedelta(days=6)
    cur = a.currency

    def L(o, d, day):
        return LegKey(o, d, day, cur)

    cases = [
        ("one-way", (L("CPH", "JFK", out_d),)),
        ("one-way", (L("JFK", "CPH", ret_d),)),
        ("round-trip", (L("CPH", "JFK", out_d), L("JFK", "CPH", ret_d))),
        ("one-way", (L("IAD", "HAM", ret_d),)),
        ("multi-city", (L("CPH", "JFK", out_d), L("IAD", "HAM", ret_d))),
        ("one-way", (L("CPH", "LHR", out_d),)),
        ("one-way", (L("LHR", "CPH", out_d + timedelta(days=3)),)),
        ("round-trip", (L("CPH", "LHR", out_d), L("LHR", "CPH", out_d + timedelta(days=3)))),
        ("multi-city", (L("CPH", "LHR", out_d), L("LGW", "CPH", out_d + timedelta(days=3)))),
        ("one-way", (L("LGW", "CPH", out_d + timedelta(days=3)),)),
    ]
    g = GoogleFlightsProvider()
    from fast_flights.parser import parse

    blocked = False
    for i, (trip, legs) in enumerate(cases):
        if i:
            time.sleep(random.uniform(2, 5))
        query = g.build_query(legs, trip)
        row = {"trip": trip, "legs": [leg.label() for leg in legs], "url": query.url()}
        resp = g.client.get(URL, params=query.params())
        row["http"] = resp.status_code
        try:
            check_blocked(resp.status_code, str(resp.url), resp.text)
        except BlockedError as exc:
            row["blocked"] = str(exc)
            blocked = True
            print(json.dumps(row), flush=True)
            continue
        try:
            res = parse(resp.text)
            priced = sorted((f for f in res if f.price), key=lambda f: f.price)
            row["parsed_count"] = len(res)
            row["cheapest"] = [
                {"price": f.price, "airlines": f.airlines,
                 "segments": [f"{s.from_airport.code}-{s.to_airport.code} {s.departure.date}" for s in f.flights]}
                for f in priced[:2]
            ]
        except Exception as exc:
            row["parse_error"] = repr(exc)[:200]
        row["raw"] = raw_sections(resp.text)
        print(json.dumps(row), flush=True)
    return 3 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
