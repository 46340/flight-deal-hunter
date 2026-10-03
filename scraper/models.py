"""Core data types."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

SEARCH_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
IATA_RE = re.compile(r"^[A-Z]{3}$")

TripType = Literal["one-way", "return"]
TicketType = Literal["single", "separate"]


class ConfigError(ValueError):
    pass


@dataclass(frozen=True, order=True)
class LegKey:
    """One one-way query. Identical keys across searches are fetched once per run."""

    origin: str
    destination: str
    date: date
    currency: str

    def label(self) -> str:
        return f"{self.origin}-{self.destination} {self.date.isoformat()}"


@dataclass
class Fare:
    price: float
    currency: str
    airlines: list[str] = field(default_factory=list)
    url: str = ""


@dataclass
class Search:
    id: str
    name: str
    status: str
    trip_type: TripType
    origins: list[str]
    destinations: list[str]
    earliest_out: date
    latest_return: date
    min_stay: int
    max_stay: int
    price_cap: float
    currency: str
    expires: date

    def is_active(self, today: date) -> bool:
        return self.status == "active" and today <= self.expires

    @classmethod
    def from_dict(cls, d: dict) -> "Search":
        try:
            sid = str(d["id"])
            if not SEARCH_ID_RE.match(sid):
                raise ConfigError(f"invalid search id {sid!r}")
            trip_type = d.get("trip_type", "return")
            if trip_type not in ("one-way", "return"):
                raise ConfigError(f"{sid}: trip_type must be 'one-way' or 'return'")
            origins = _iata_list(d["origins"], sid, "origins")
            destinations = _iata_list(d["destinations"], sid, "destinations")
            earliest_out = date.fromisoformat(d["earliest_out"])
            latest_return = date.fromisoformat(d["latest_return"])
            if latest_return < earliest_out:
                raise ConfigError(f"{sid}: latest_return is before earliest_out")
            min_stay = int(d.get("min_stay", 1))
            max_stay = int(d.get("max_stay", 7))
            if min_stay < 0 or max_stay < min_stay:
                raise ConfigError(f"{sid}: need 0 <= min_stay <= max_stay")
            if "expires" in d:
                expires = date.fromisoformat(d["expires"])
            else:
                created = date.fromisoformat(d["created"])
                expires = created + timedelta(days=int(d.get("tracking_days", 10)))
            return cls(
                id=sid,
                name=str(d.get("name", sid)),
                status=d.get("status", "active"),
                trip_type=trip_type,
                origins=origins,
                destinations=destinations,
                earliest_out=earliest_out,
                latest_return=latest_return,
                min_stay=min_stay,
                max_stay=max_stay,
                price_cap=float(d["price_cap"]),
                currency=str(d.get("currency", "DKK")).upper(),
                expires=expires,
            )
        except KeyError as exc:
            raise ConfigError(f"search {d.get('id', '?')}: missing field {exc}") from None
        except ValueError as exc:
            if isinstance(exc, ConfigError):
                raise
            raise ConfigError(f"search {d.get('id', '?')}: {exc}") from None


def _iata_list(values, sid: str, name: str) -> list[str]:
    out = []
    for v in values:
        code = str(v).strip().upper()
        if not IATA_RE.match(code):
            raise ConfigError(f"{sid}: bad IATA code {v!r} in {name}")
        if code not in out:
            out.append(code)
    if not out:
        raise ConfigError(f"{sid}: {name} is empty")
    return out


@dataclass
class Trip:
    """A candidate itinerary built from one or two one-way legs."""

    out: LegKey
    out_fare: Fare
    ret: LegKey | None = None
    ret_fare: Fare | None = None
    single: Fare | None = None  # set after re-pricing as one ticket

    @property
    def is_return(self) -> bool:
        return self.ret is not None

    @property
    def legs(self) -> tuple[LegKey, ...]:
        return (self.out,) if self.ret is None else (self.out, self.ret)

    @property
    def separate_total(self) -> float:
        return self.out_fare.price + (self.ret_fare.price if self.ret_fare else 0.0)

    @property
    def itinerary_kind(self) -> str:
        if self.ret is None:
            return "one-way"
        if self.out.origin == self.ret.destination and self.out.destination == self.ret.origin:
            return "round-trip"
        return "multi-city"

    @property
    def ticket_type(self) -> TicketType:
        if self.ret is None:
            return "single"
        if self.single is not None and self.single.price <= self.separate_total:
            return "single"
        return "separate"

    @property
    def final_price(self) -> float:
        if self.single is not None:
            return min(self.single.price, self.separate_total)
        return self.separate_total

    @property
    def airlines(self) -> list[str]:
        if self.ticket_type == "single" and self.single is not None:
            return self.single.airlines
        names: list[str] = []
        for f in (self.out_fare, self.ret_fare):
            for a in (f.airlines if f else []):
                if a not in names:
                    names.append(a)
        return names

    @property
    def links(self) -> list[str]:
        if self.ret is None:
            return [self.out_fare.url]
        if self.ticket_type == "single" and self.single is not None:
            return [self.single.url]
        return [self.out_fare.url, self.ret_fare.url]

    @property
    def key(self) -> str:
        parts = [f"{self.out.origin}-{self.out.destination}-{self.out.date.isoformat()}"]
        if self.ret is not None:
            parts.append(f"{self.ret.origin}-{self.ret.destination}-{self.ret.date.isoformat()}")
        return "|".join(parts)
