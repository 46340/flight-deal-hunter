"""Download OurAirports airports.csv and write web/data/airports.json.

Keeps large and medium airports that have scheduled service and an IATA code.
The UI shows large airports by default and medium ones behind a toggle.

Usage: python scripts/build_airports.py [--csv path/to/airports.csv]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

SOURCE_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
OUT_PATH = Path(__file__).resolve().parent.parent / "web" / "data" / "airports.json"
KEEP_TYPES = {"large_airport", "medium_airport"}


def parse_airports(csv_text: str) -> list[dict]:
    airports = []
    seen: set[str] = set()
    for row in csv.DictReader(io.StringIO(csv_text)):
        iata = (row.get("iata_code") or "").strip().upper()
        if row.get("type") not in KEEP_TYPES:
            continue
        if row.get("scheduled_service") != "yes":
            continue
        if len(iata) != 3 or not iata.isalpha() or iata in seen:
            continue
        try:
            lat = round(float(row["latitude_deg"]), 4)
            lon = round(float(row["longitude_deg"]), 4)
        except (KeyError, ValueError):
            continue
        seen.add(iata)
        airports.append(
            {
                "iata": iata,
                "name": row.get("name", "").strip(),
                "city": (row.get("municipality") or "").strip(),
                "country": (row.get("iso_country") or "").strip(),
                "lat": lat,
                "lon": lon,
                "type": row["type"],
            }
        )
    airports.sort(key=lambda a: a["iata"])
    return airports


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", help="use a local airports.csv instead of downloading")
    args = parser.parse_args()

    if args.csv:
        text = Path(args.csv).read_text(encoding="utf-8")
    else:
        try:
            with urllib.request.urlopen(SOURCE_URL, timeout=60) as resp:
                text = resp.read().decode("utf-8")
        except urllib.error.URLError as exc:
            print(f"Download failed: {exc}", file=sys.stderr)
            print(
                "On macOS with python.org Python, run 'Install Certificates.command' from the Python folder, "
                f"or download {SOURCE_URL} yourself and pass --csv.",
                file=sys.stderr,
            )
            return 1

    airports = parse_airports(text)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(airports, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    large = sum(1 for a in airports if a["type"] == "large_airport")
    print(f"Wrote {len(airports)} airports ({large} large, {len(airports) - large} medium) to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
