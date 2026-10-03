import json
from datetime import date

from scraper.blocking import BlockDetector, BlockedError
from scraper.models import Fare
from scraper.providers.base import EmptyResponse, NoFlights, Provider
from scraper.providers.mock import MockProvider
from scraper.run import Runner, execute

from .conftest import TODAY, make_search


class Scripted(Provider):
    """Replays a list of outcomes: a number (price), 'none', 'empty', 'error', 'block'."""

    def __init__(self, script, name="scripted"):
        self.script = list(script)
        self.name = name

    def _next(self, currency):
        step = self.script.pop(0) if self.script else 500
        if step == "none":
            raise NoFlights()
        if step == "empty":
            raise EmptyResponse()
        if step == "error":
            raise ConnectionError("boom")
        if step == "block":
            raise BlockedError("captcha")
        return Fare(step, currency, ["X"], "u")

    def one_way(self, leg):
        return self._next(leg.currency)

    def itinerary(self, legs, kind):
        return self._next(legs[0].currency)


def test_block_detector():
    d = BlockDetector(3)
    assert not d.empty("a")
    assert d.ok() == ["a"]
    assert not d.empty("b") and not d.empty("c")
    assert d.empty("d")
    assert d.discard() == ["b", "c", "d"]


def legs(n):
    s = make_search(earliest_out="2026-11-01", latest_return="2026-12-31", trip_type="one-way")
    from scraper.planner import legs_for_search
    return legs_for_search(s, TODAY)[:n]


def test_empty_streak_becomes_block_and_is_not_recorded(settings):
    settings["block_threshold"] = 4
    ls = legs(10)
    r = Runner([Scripted([100, "none", "empty", "empty", "empty", "empty"])], settings, sleep=False)
    try:
        r.fetch_legs(ls, log=lambda *_: None)
    except BlockedError:
        pass
    r.finish()
    assert r.state.blocked
    assert r.state.fares == {ls[0]: r.state.fares[ls[0]], ls[1]: None}
    assert r.state.fares[ls[0]].price == 100


def test_short_empty_streak_is_trusted_as_no_flights(settings):
    ls = legs(4)
    r = Runner([Scripted(["empty", "empty", 300, "empty"])], settings, sleep=False)
    r.fetch_legs(ls, log=lambda *_: None)
    r.finish()
    assert not r.state.blocked
    assert [r.state.fares[leg] is None for leg in ls] == [True, True, False, True]


def test_failed_leg_is_not_recorded_as_no_flights(settings):
    settings["max_retries"] = 1
    ls = legs(2)
    r = Runner([Scripted(["error", "error", 700])], settings, sleep=False)
    r.fetch_legs(ls, log=lambda *_: None)
    r.finish()
    assert ls[0] not in r.state.fares
    assert ls[0] in r.state.leg_errors
    assert r.state.fares[ls[1]].price == 700


def test_retry_then_success(settings):
    ls = legs(1)
    r = Runner([Scripted(["error", 450])], settings, sleep=False)
    r.fetch_legs(ls, log=lambda *_: None)
    assert r.state.fares[ls[0]].price == 450 and not r.state.leg_errors


def test_fallback_provider_after_block(settings):
    ls = legs(3)
    primary = Scripted([100, "block"], name="google")
    backup = Scripted([200, 300], name="paid")
    r = Runner([primary, backup], settings, sleep=False)
    r.fetch_legs(ls, log=lambda *_: None)
    r.finish()
    assert [r.state.fares[leg].price for leg in ls] == [100, 200, 300]
    assert r.state.provider_used == {"google", "paid"}
    assert not r.state.blocked


def test_mock_end_to_end(tmp_path, settings):
    s = make_search(id="e2e", origins=["CPH", "BLL"], destinations=["JFK", "IAD"],
                    earliest_out="2026-11-02", latest_return="2026-11-09", min_stay=3, max_stay=5, price_cap=4000)
    summary = execute([s], settings, [MockProvider(seed=3)], tmp_path, TODAY, sleep=False, log=lambda *_: None)
    assert summary["status"] == "ok"
    res = json.loads((tmp_path / "results" / "e2e.json").read_text())
    assert res["runs"][-1]["status"] == "ok"
    assert len(res["cheapest_per_run"]) == 1
    assert all(d["price"] <= 4000 for d in res["deals"])
    assert json.loads((tmp_path / "runs.json").read_text())["runs"][-1]["queries"] == summary["queries"]


def test_mock_blocked_run_keeps_previous_deals(tmp_path, settings):
    s = make_search(id="blk", origins=["CPH", "BLL"], destinations=["JFK", "IAD"],
                    earliest_out="2026-11-02", latest_return="2026-11-09", min_stay=3, max_stay=5, price_cap=6000)
    execute([s], settings, [MockProvider(seed=3)], tmp_path, TODAY, sleep=False, log=lambda *_: None)
    before = json.loads((tmp_path / "results" / "blk.json").read_text())["deals"]
    assert before
    summary = execute([s], settings, [MockProvider(seed=4, block_after=10)], tmp_path, TODAY,
                      sleep=False, log=lambda *_: None)
    assert summary["status"] == "blocked"
    after = json.loads((tmp_path / "results" / "blk.json").read_text())
    assert after["runs"][-1]["status"] == "blocked"
    assert len(after["cheapest_per_run"]) == 1
    flipped = [d for d in after["deals"] if not d["available"]]
    # Only deals whose legs were all answered in the first 10 queries may flip.
    for d in flipped:
        assert d["out_date"] == "2026-11-02"
