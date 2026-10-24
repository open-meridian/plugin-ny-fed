"""The NY Fed's answer as the plugin reads it: each reference rate it
states, every figure a `Decimal` from the answer's own text, never a float.

The markets data API answers `{"refRates": [...]}`, one object per rate type
and effective date:

- **SOFR, TGCR, BGCR, OBFR and EFFR**: `percentRate`, its 1st, 25th, 75th
  and 99th percentiles (`percentPercentile1` ...) and `volumeInBillions`,
  each where published -- EFFR before 2016 states no percentile or volume,
  but an intraday low and high and a standard deviation, which the lake's
  rate has no field for and the raw answer keeps; EFFR also states the
  FOMC's target range (`targetRateFrom`, `targetRateTo`), which is the
  Federal Reserve Board's to publish, and the plugin leaves it to it;
- **SOFRAI**: the SOFR 30, 90 and 180-day averages and the SOFR Index, for
  the effective date they are published on;
- `revisionIndicator`: `r` on a rate the NY Fed revised, else empty; and
  where one applies, `footnoteId`.

An object the plugin cannot read -- no type or date, or a figure that is no
number -- is kept aside as unread, said on the Datasets page, never
recorded.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

#: The percentiles the NY Fed states, by their field.
PERCENTILES = {
    "percentPercentile1": 1,
    "percentPercentile25": 25,
    "percentPercentile75": 75,
    "percentPercentile99": 99,
}
#: The fields a rate's value may be in.
VALUES = ("percentRate", "average30day", "average90day", "average180day", "index")


class NotRates(Exception):  # noqa: N818 - what the answer was
    """The answer is not the API's reference rates."""


@dataclass(frozen=True)
class Published:
    """One object of the answer: a rate type on its effective date, its
    values by field, its percentiles, its volume in billions of dollars, and
    whether the NY Fed marks it revised."""

    rate_type: str
    day: date
    values: dict[str, Decimal] = field(default_factory=dict)
    percentiles: dict[int, Decimal] = field(default_factory=dict)
    volume_billions: Decimal | None = None
    revised: bool = False
    footnote: str = ""


@dataclass(frozen=True)
class Answer:
    """What one answer states: each rate, in date order, the days it covers,
    and the objects it could not read."""

    rates: tuple[Published, ...]
    unread: tuple[str, ...] = ()

    @property
    def days(self) -> list[date]:
        return sorted({r.day for r in self.rates})

    def latest(self, rate_type: str) -> date | None:
        days = [r.day for r in self.rates if r.rate_type == rate_type]
        return max(days) if days else None


def _number(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise InvalidOperation(repr(value))
    return Decimal(str(value))


def parse(text: str) -> Answer:
    """The answer's rates; NotRates where it is not the API's reference rates."""
    try:
        held = json.loads(text, parse_float=Decimal, parse_int=Decimal)
    except ValueError as broken:
        raise NotRates(f"not JSON: {broken}") from broken
    if not isinstance(held, dict) or not isinstance(held.get("refRates"), list):
        raise NotRates("no refRates in the answer")
    rates: list[Published] = []
    unread: list[str] = []
    for one in held["refRates"]:
        try:
            rates.append(_published(one))
        except (KeyError, ValueError, TypeError, InvalidOperation):
            unread.append(json.dumps(one, default=str, sort_keys=True)[:200])
    rates.sort(key=lambda r: (r.day, r.rate_type))
    return Answer(tuple(rates), tuple(unread))


def _published(one: Any) -> Published:
    if not isinstance(one, dict):
        raise TypeError("not an object")
    rate_type = str(one["type"]).strip().upper()
    day = date.fromisoformat(str(one["effectiveDate"]))
    values = {name: _number(one[name]) for name in VALUES if one.get(name) is not None}
    if not values:
        raise ValueError("no rate")
    percentiles = {
        p: _number(one[name]) for name, p in PERCENTILES.items() if one.get(name) is not None
    }
    volume = one.get("volumeInBillions")
    return Published(
        rate_type=rate_type,
        day=day,
        values=values,
        percentiles=percentiles,
        volume_billions=None if volume is None else _number(volume),
        revised=str(one.get("revisionIndicator") or "").strip().lower() == "r",
        footnote=str(one.get("footnoteId") or ""),
    )
