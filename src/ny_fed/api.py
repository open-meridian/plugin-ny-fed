"""The Federal Reserve Bank of New York's markets data API, where the
reference rates are published, and its stand-in.

One kind of request is made, and nothing else: every reference rate over a
range of effective dates, as JSON --
`/api/rates/all/search.json?startDate=<day>&endDate=<day>` -- SOFR, EFFR,
OBFR, TGCR, BGCR and SOFRAI (the SOFR averages and index) in one answer. A
range with no rate, a weekend or a holiday, is answered with an empty list.

The current rates are a range ending today, read at the publication windows
(feed.py). The API states no Last-Modified and no publication time, and
answers every request in full (`Cache-Control: no-store`), so the plugin
tells what changed by what the answer states (feed.py).

Read from the NY Fed itself: no key, no account, and its terms are its Terms
of Use (docs/terms.md). It states no rate limit for the API; the plugin asks
one request at a time, at most one every two seconds, says who it is in its
User-Agent, and reads the current rates every five minutes in the
publication windows and hourly otherwise. The standard library's client: the
SDK carries none, and one kind of request needs nothing more.

`SyntheticApi` answers from the real response committed under responses/,
recorded on 2026-10-23 (responses/index.json): every reference rate from 3
August to 23 October 2026. A request for a range is answered with the
recorded rates in it, as the API writes them, and its current range ends on
23 October 2026 whatever the clock says, so the plugin's tests and its e2e
run on it, offline, the same on any day.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from importlib import resources
from typing import Any, Protocol

BASE = "https://markets.newyorkfed.org"
SEARCH = "/api/rates/all/search.json"
USER_AGENT = "meridian-ny-fed (+https://github.com/open-meridian/plugin-ny-fed)"
#: The least time between two requests, in seconds.
SPACING = 2.0
#: How long one request may take.
TIMEOUT = 60.0
#: The most of an answer read: a year of every rate is about 340 kB.
MOST_BYTES = 16 * 1024 * 1024
#: How many days the current range reaches back: a revision to a rate of the
#: last week or so is read as the same row's next version.
CURRENT_DAYS = 10


def path_for(start: date, end: date) -> str:
    """The address of every reference rate from `start` to `end`."""
    return f"{SEARCH}?startDate={start.isoformat()}&endDate={end.isoformat()}"


class Unreachable(Exception):  # noqa: N818 - what the NY Fed's API was
    """The API could not be asked: no answer, or not in time."""


@dataclass(frozen=True)
class Fetched:
    """One answer of the API's, as received."""

    path: str
    status: int
    body: bytes
    fetched_at: datetime
    date: str = ""

    @property
    def url(self) -> str:
        return BASE + self.path

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class Api(Protocol):
    mode: str

    def current(self, today: date) -> tuple[date, date]: ...

    def earliest(self) -> date | None: ...

    async def get(self, path: str) -> Fetched: ...


def utc_now() -> datetime:
    return datetime.now(UTC)


class LiveApi:
    """The NY Fed's markets data API itself."""

    mode = "live"

    def __init__(self, now: Callable[[], datetime] = utc_now) -> None:
        self._now = now
        self._lock = asyncio.Lock()
        self._last = 0.0

    def current(self, today: date) -> tuple[date, date]:
        """The current range: the last `CURRENT_DAYS` days to today."""
        return today - timedelta(days=CURRENT_DAYS), today

    def earliest(self) -> date | None:
        """The first day it states: the catalogue's, the API's own."""
        return None

    async def get(self, path: str) -> Fetched:
        async with self._lock:
            wait = self._last + SPACING - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                return await asyncio.to_thread(self._get, path)
            finally:
                self._last = time.monotonic()

    def _get(self, path: str) -> Fetched:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        request = urllib.request.Request(BASE + path, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:  # noqa: S310 - the NY Fed's https address
                body = answer.read(MOST_BYTES + 1)
                status = answer.status
                said = answer.headers
        except urllib.error.HTTPError as refused:
            body = refused.read(MOST_BYTES + 1) if refused.fp else b""
            status, said = refused.code, refused.headers
        except (urllib.error.URLError, TimeoutError, OSError) as failed:
            reason = getattr(failed, "reason", failed)
            raise Unreachable(f"{BASE}{path}: {type(reason).__name__}") from failed
        if len(body) > MOST_BYTES:
            raise Unreachable(f"{BASE}{path}: answered more than {MOST_BYTES} bytes")
        return Fetched(path, status, body, self._now(), date=said.get("Date", "") if said else "")


def write(rates: list[dict[str, Any]]) -> str:
    """Rates as the API writes them: each figure as stated, never through a
    float."""

    def value(held: Any) -> str:
        if isinstance(held, Decimal):
            return str(held)
        return json.dumps(held)

    objects = [
        "{ " + " ,".join(f"{json.dumps(k)}: {value(v)}" for k, v in one.items()) + " }"
        for one in rates
    ]
    return '{ "refRates": [ ' + ", ".join(objects) + " ] }"


class SyntheticApi:
    """The response committed under responses/: each range answered with
    the recorded rates in it."""

    mode = "synthetic"

    def __init__(self, now: Callable[[], datetime] = utc_now) -> None:
        self._now = now
        held = resources.files(__package__).joinpath("responses")
        index = json.loads(held.joinpath("index.json").read_text(encoding="utf-8"))
        entry = index["response"]
        text = gzip.decompress(held.joinpath(entry["file"]).read_bytes()).decode("utf-8")
        loaded = json.loads(text, parse_float=Decimal, parse_int=Decimal)
        self.rates: list[dict[str, Any]] = loaded["refRates"]
        self.said = str(entry["date"])
        self.first_day = date.fromisoformat(entry["first_day"])
        self.last_day = date.fromisoformat(entry["last_day"])
        self.asked: list[str] = []

    def current(self, today: date) -> tuple[date, date]:
        """The current range of the recording: its last `CURRENT_DAYS` days."""
        return self.last_day - timedelta(days=CURRENT_DAYS), self.last_day

    def earliest(self) -> date | None:
        """The first day the recording holds, from which sample data's
        history is backfilled."""
        return self.first_day

    def answer(self, start: date, end: date) -> list[dict[str, Any]]:
        """The recorded rates from `start` to `end`, newest first, as the API orders them."""
        return [
            one
            for one in self.rates
            if start.isoformat() <= str(one.get("effectiveDate", "")) <= end.isoformat()
        ]

    async def get(self, path: str) -> Fetched:
        self.asked.append(path)
        if not path.startswith(SEARCH + "?"):
            return Fetched(path, 404, b'{"error": "not found"}', self._now(), self.said)
        query = dict(part.partition("=")[::2] for part in path.split("?", 1)[1].split("&"))
        try:
            start = date.fromisoformat(query.get("startDate", ""))
            end = date.fromisoformat(query.get("endDate", ""))
        except ValueError:
            return Fetched(path, 400, b'{"error": "invalid date"}', self._now(), self.said)
        body = write(self.answer(start, end))
        return Fetched(path, 200, body.encode(), self._now(), self.said)


def api(synthetic: bool, now: Callable[[], datetime] = utc_now) -> Api:
    return SyntheticApi(now) if synthetic else LiveApi(now)
