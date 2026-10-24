"""The reference rates as the lake's rates (contract v27, `Rate`), built
through the SDK's rates helpers (`meridian.roles.data.rates`, ruling 345).

Each object of the NY Fed's answer (published.py) becomes one row, or for
SOFRAI one per figure it states, each about one of the nine referential
records (declared.py, `SUBJECTS`):

- **SOFR, EFFR, OBFR, TGCR and BGCR**: kind `fixing`, its value the rate in
  per cent as stated (3.90 is 3.90 `percent`), its convention the money
  market's -- actual/360, simple (`rates.MONEY_MARKET`), as the NY Fed
  states each an annualised rate on an actual/360 basis -- its 1st, 25th,
  75th and 99th percentiles and its volume, where published. The volume is
  stated in billions of dollars and recorded as the dollars it is, exactly
  (2945 is USD 2,945,000,000,000). No tenor: each is an overnight rate, its
  own record;
- **the SOFR 30, 90 and 180-day averages**: kind `average`, each its own
  record, in per cent, convention the money market's: the NY Fed compounds
  SOFR over the period and states the result as an annualised actual/360
  rate;
- **the SOFR Index**: kind `index_level`, its level an `index` value based at
  1.00000000 on 2 April 2018, as the NY Fed defines it; its convention the
  one it compounds, the money market's -- each day's SOFR accrues on an
  actual/360 basis, simple, compounded day by day -- since the lake keeps
  no rate without one.

**Business date** the effective date, as the NY Fed states it; **valid from
and until** New York's day for it (`day_time_zone` America/New_York, ending
at midnight). **Row key** the SDK's: the source, the kind, no tenor, the
convention, the date and the record (`nyfed:fixing:-:act_360:simple:
2026-10-22@INS-...`), never its published time, so a rate the NY Fed revises
is the same row's next version, and an identical repeat is answered
unchanged. **Source time** `published`, where the plugin knows it (feed.py),
and **raw** the answer it was first read from.

A rate whose record the deployment does not hold is not sent: the SDK
reports the miss once a day, and its rates wait until it is held.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from meridian import Money
from meridian.operations import Rate
from meridian.roles.data import rates

from .declared import SUBJECTS, Subject
from .published import Published
from .raw import First

#: The SOFR Index's base, as the NY Fed states it.
INDEX_BASE = "2018-04-02=1.00000000"


@dataclass(frozen=True)
class Stated:
    """One figure the answer states for one record, before it is a row."""

    subject: Subject
    published: Published
    value: Decimal


def stated(answer: Iterable[Published], days: Iterable[date] | None = None) -> list[Stated]:
    """Each figure the answer states for one of the nine records, on `days`
    where given."""
    wanted = set(days) if days is not None else None
    out: list[Stated] = []
    for one in answer:
        if wanted is not None and one.day not in wanted:
            continue
        for subject in SUBJECTS:
            if subject.rate_type == one.rate_type and subject.field in one.values:
                out.append(Stated(subject, one, one.values[subject.field]))
    return out


def volume(billions: Decimal | None) -> Money | None:
    """A volume stated in billions of dollars, as the dollars it is."""
    if billions is None:
        return None
    return Money(billions * 1_000_000_000, "USD")


def to_rate(
    feed: rates.Feed,
    key: str,
    one: Stated,
    instrument_id: str,
    first: Callable[[Stated, str], First],
) -> Rate:
    """One figure as a row of `key`'s dataset about `instrument_id`; `first`
    says where the figure was first read, given it and its row key."""
    subject, published = one.subject, one.published

    def made(published_ns: int = 0, raw_key: str = "") -> Rate:
        fixing = subject.kind == "fixing"
        return feed.rate(
            instrument_id,
            key,
            subject.kind,
            (
                rates.index_level(one.value, INDEX_BASE)
                if subject.kind == "index_level"
                else rates.percent(one.value)
            ),
            business_date=published.day,
            published_ns=published_ns,
            raw_key=raw_key,
            convention=rates.MONEY_MARKET,
            volume=volume(published.volume_billions) if fixing else None,
            percentiles=(published.percentiles or None) if fixing else None,
        )

    unsaid = made()
    assert unsaid.meta is not None
    where = first(one, unsaid.meta.row_key)
    return made(where.published_ns, where.key)


def to_rates(
    feed: rates.Feed,
    key: str,
    figures: Iterable[Stated],
    instruments: Mapping[str, str],
    first: Callable[[Stated, str], First],
) -> tuple[list[Rate], tuple[str, ...]]:
    """The rows `figures` state, each about its record's instrument; and the
    codes of the records not held, whose figures wait."""
    rows: list[Rate] = []
    unresolved: dict[str, None] = {}
    for one in figures:
        instrument = instruments.get(one.subject.code, "")
        if not instrument:
            unresolved[one.subject.code] = None
            continue
        rows.append(to_rate(feed, key, one, instrument, first))
    return rows, tuple(unresolved)
