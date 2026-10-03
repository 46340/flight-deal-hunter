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


def save_fixture(path: Path, text: str) -> None:
    from selectolax.lexbor import LexborHTMLParser

    script = LexborHTMLParser(text).css_first(r"script.ds\:1")
    body = script.html if script is not None else "<!-- no ds:1 script -->"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"<html><body>{body}</body></html>\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out-date", type=date.fromisoformat, default=date.today() + timedelta(days=32))
    p.add_argument("--ret-date", type=date.fromisoformat)
    p.add_argument("--currency", default="DKK")
    p.add_argument("--single-ticket", action="store_true", help="hide separate/self-transfer itineraries in round-trip and multi-city queries")
    p.add_argument("--save-dir", type=Path, help="save each page's data script as a trimmed HTML fixture")
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
    from scraper.providers.google_parse import parse_offers

    blocked = False
    for i, (trip, legs) in enumerate(cases):
        if i:
            time.sleep(random.uniform(2, 5))
        query = g.build_query(legs, trip, single_ticket_only=a.single_ticket and trip != "one-way")
        row = {"trip": trip, "legs": [leg.label() for leg in legs], "url": query.url()}
        resp = g.client.get(URL, params=query.params(), headers=g.headers)
        row["http"] = resp.status_code
        try:
            check_blocked(resp.status_code, str(resp.url), resp.text)
        except BlockedError as exc:
            row["blocked"] = str(exc)
            blocked = True
            print(json.dumps(row), flush=True)
            continue
        try:
            offers = parse_offers(resp.text)
            row["offers"] = len(offers)
            row["cheapest"] = [{"price": o.price, "airlines": o.airlines, "section": o.section} for o in offers[:3]]
        except Exception as exc:
            row["parse_error"] = repr(exc)[:200]
        if a.save_dir:
            save_fixture(a.save_dir / f"{i:02d}_{trip}_{'_'.join(leg.origin + leg.destination for leg in legs)}.html", resp.text)
        print(json.dumps(row), flush=True)
    return 3 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
