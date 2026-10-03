import json
from datetime import date
from pathlib import Path

import pytest

from scraper.models import Search
from scraper.run import DEFAULT_SETTINGS

FIXTURES = Path(__file__).parent / "fixtures"


def make_search(**overrides) -> Search:
    d = {
        "id": "test",
        "status": "active",
        "created": "2026-10-01",
        "tracking_days": 30,
        "trip_type": "return",
        "origins": ["CPH"],
        "destinations": ["JFK"],
        "earliest_out": "2026-11-01",
        "latest_return": "2026-11-10",
        "min_stay": 1,
        "max_stay": 7,
        "price_cap": 3000,
        "currency": "DKK",
    }
    d.update(overrides)
    return Search.from_dict(d)


@pytest.fixture
def settings():
    return dict(DEFAULT_SETTINGS)


@pytest.fixture
def estimate_cases():
    return json.loads((FIXTURES / "estimate_cases.json").read_text())["cases"]


TODAY = date(2026, 10, 3)
