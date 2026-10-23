"""The NY Fed's reference rates into the lake: each day's pushed when the NY
Fed publishes it, its history backfilled on the first run, and any past day
recorded when the lake wants it (W10.4, W10.7), through the SDK's rates
helpers (`meridian.roles.data.rates`).

**Push.** The current rates -- the last ten days to today -- are read at
start, then every five minutes in the NY Fed's publication windows (08:00 to
10:30 ET for the rates, 14:25 to 15:15 ET for a revision) and hourly
otherwise (schedule.py). The API states no Last-Modified, so an answer
stating what the last one stated records nothing and is not kept again; one
stating something new is kept and recorded whole, in batches of at most 500,
and the lake answers each rate it holds unchanged. A rate the NY Fed revises
-- by 14:30 ET on its day of publication, when it is out by more than a
basis point -- is a new value under the same row key: the lake keeps it as
the row's next version, never in place.

**Published time.** The NY Fed states none. A rate the plugin sees appear --
one absent from its previous read of the current rates, at most 70 minutes
earlier, on the rate's day of publication -- is stated `published` at the
moment it was first read: within five minutes of its publication in the
windows, within the hour otherwise. A rate read later, by the backfill or a
want, or first seen after a pause, states no published time rather than a
wrong one. A revision is published later than the rate it revises, so the
lake orders their versions by it.

**History.** On the first run the plugin reads every rate the NY Fed
publishes, a year per request, newest first, from today back to EFFR's first
day (3 July 2000), and records it; each year read is noted in storage, so a
restart goes on where it stopped and a finished backfill is not read again.

**Subjects.** Before anything is recorded, each of the nine records is
resolved by the NY Fed's code as a symbol at `nyfed`, the platform's seeded
referential records (the SDK's `rates.Feed.subject`); one the deployment
does not hold is reported missing once a day, with why, and its rates wait.
The plugin mints nothing.

**Wants.** The lake asks for what a reader read and it does not hold: a
business date, a range, or the latest. The plugin covers its nine records'
rates and declines anything else `not_covered`. A weekend asked is declined
`source_silent` without a request; a day before 3 July 2000
`beyond_history`; the rest are read from the API in one request, at most a
quarter, and recorded against the want, a record the NY Fed stated nothing
for on those days declined `source_silent`. A standing want asks the
records kept current, which the push does, until it is withdrawn. The SDK's
`Wants` keeps the wants, declines by reason, sends the batches and counts
them; only the NY Fed's part is here.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import meridian
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles import data
from meridian.roles.data import rates

from .api import Api, Fetched, Unreachable, path_for, utc_now
from .convert import Stated, stated, to_rates
from .declared import (
    DAY_TIME_ZONE,
    EARLIEST,
    NYFED_RATES,
    RATE,
    SUBJECTS,
    SYMBOL_SOURCE,
    Subject,
)
from .published import Answer, NotRates, parse
from .raw import First, RawStore

log = logging.getLogger("ny_fed")

NEW_YORK = ZoneInfo(DAY_TIME_ZONE)
#: The most days one want is answered for: a quarter.
MOST_DAYS = 92
#: How many published-minus-valid times are kept for the Lag figure.
LAGS = 2000
#: How recent the previous read of the current rates must be for a rate first
#: seen now to be stated published now: an hour's check, and its slack.
SEEN_WITHIN_SECONDS = 70 * 60
#: How long after its effective date a fixing may first be published: the
#: next business day, past a weekend and a holiday.
RELEASE_DAYS = 4


def _ns(moment: datetime) -> int:
    return int(moment.timestamp() * 1_000_000) * 1000


def new_york_day(at_ns: int) -> date:
    """The day in New York at a moment."""
    return datetime.fromtimestamp(at_ns // 10**9, NEW_YORK).date()


def day_start_ns(day: date) -> int:
    return _ns(datetime.combine(day, time(0, 0), NEW_YORK))


def next_weekday(day: date) -> date:
    following = day + timedelta(days=1)
    while following.weekday() >= 5:
        following += timedelta(days=1)
    return following


@dataclass
class Held:
    """One of the nine records as the plugin last saw it: the deployment's
    instrument for it, or why there is none, and its latest day stated."""

    subject: Subject
    instrument_id: str = ""
    miss: str = ""
    latest_day: date | None = None


@dataclass(frozen=True)
class Outcome:
    recorded: int = 0
    restated: int = 0
    unchanged: int = 0
    unresolved: tuple[str, ...] = ()


@dataclass
class Status:
    """What the plugin last did, for its pages; held in memory, lost on a
    restart and read again by the first check."""

    mode: str = "live"
    started_at: datetime | None = None
    checked_at: datetime | None = None
    #: When the API last answered with rates, and when it last answered.
    read_at: datetime | None = None
    error: str = ""
    #: The current range's first and latest effective date with a rate.
    first_day: date | None = None
    latest_day: date | None = None
    held: dict[str, Held] = field(default_factory=lambda: {s.code: Held(s) for s in SUBJECTS})
    #: The latest effective date stated, by the API's rate type.
    latest_by_type: dict[str, date] = field(default_factory=dict)
    #: Objects that named a rate but held none that reads, each with how often seen.
    unread: dict[str, int] = field(default_factory=dict)
    fetches: int = 0
    unchanged_reads: int = 0
    #: Published minus valid-from, in seconds, of each rate first read with
    #: its published time since the plugin started.
    lags: list[int] = field(default_factory=list)
    #: The backfill: the years read, whether it finished, and its last error.
    backfill_years: list[int] = field(default_factory=list)
    backfill_done: bool = False
    backfill_error: str = ""
    #: Whether the backfill waits for a record the deployment does not hold.
    backfill_waiting: bool = False
    revisions: int = 0


class _Asking:
    """The plugin, as the SDK's rates helpers call it, keeping why each
    record did not resolve for the Records tab."""

    def __init__(self, plugin: Any, status: Status) -> None:
        self._plugin = plugin
        self._status = status

    def __getattr__(self, name: str) -> Any:
        return getattr(self._plugin, name)

    async def resolve_identifier(self, **asked: Any) -> Any:
        found = await self._plugin.resolve_identifier(**asked)
        code = asked["identifiers"][0].value
        held = self._status.held.get(code)
        if held is not None and not (found.found and found.instrument_id):
            reason = found.miss_reason or ops.MISS_REASON_NOT_FOUND
            held.miss = ops.MissReason.Name(reason).removeprefix("MISS_REASON_").lower()
        return found


class Feed:
    """The plugin's work, on its typed operations -- `plugin` is the
    connected `meridian.Plugin`, or the suite's `Recorder` in its tests --
    reading the API, resolving, recording, backfilling, answering wants."""

    def __init__(
        self,
        plugin: Any,
        api: Api,
        raw: RawStore,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self.plugin = plugin
        self.api = api
        self.raw = raw
        self.now = now
        self.status = Status(mode=api.mode, started_at=now())
        self.wants = data.Wants(plugin, (NYFED_RATES,), clock_ns=self.now_ns)
        self.rates = rates.Feed(
            _Asking(plugin, self.status),
            SYMBOL_SOURCE,
            wants=self.wants,
            day_zone=DAY_TIME_ZONE,
            clock_ns=self.now_ns,
        )
        self._current_digest = ""
        self._recorded_digest = ""
        self._current: Answer | None = None
        self._current_key = ""
        self._previous_read_ns = 0

    def now_ns(self) -> int:
        return _ns(self.now())

    @property
    def dataset(self) -> str:
        return self.wants.dataset(NYFED_RATES)

    def today(self) -> date:
        return new_york_day(self.now_ns())

    def use(self, api: Api) -> None:
        """Read from `api` from now on: sample data turned on or off."""
        if api.mode != self.api.mode:
            self.api = api
            self.status.mode = api.mode
            self._current_digest = self._recorded_digest = ""
            self._current, self._previous_read_ns = None, 0

    # ── Reading the API ─────────────────────────────────────────────────

    async def read(self, start: date, end: date) -> tuple[Answer, Fetched]:
        """The rates from `start` to `end`, and the answer. Unreachable or
        NotRates otherwise."""
        fetched = await self.api.get(path_for(start, end))
        self.status.fetches += 1
        if fetched.status != 200:
            self.raw.keep(fetched)
            raise Unreachable(f"{fetched.url} answered {fetched.status}")
        return parse(fetched.text), fetched

    # ── Resolving ───────────────────────────────────────────────────────

    async def resolve(self) -> dict[str, str]:
        """Each record's instrument, resolved where not yet (the SDK's
        `rates.Feed.subject`: once per process, a miss reported once a day)."""
        for code, held in self.status.held.items():
            if held.instrument_id:
                continue
            found = await self.rates.subject(
                ("symbol", code, SYMBOL_SOURCE),
                description=held.subject.name,
                instrument_type=held.subject.instrument_type,
            )
            if found:
                held.instrument_id, held.miss = found, ""
            elif not held.miss:
                held.miss = "not_found"
        return self.instruments()

    def instruments(self) -> dict[str, str]:
        return {c: h.instrument_id for c, h in self.status.held.items() if h.instrument_id}

    # ── Recording ───────────────────────────────────────────────────────

    def _note(self, answer: Answer) -> None:
        for line in answer.unread:
            self.status.unread[line] = self.status.unread.get(line, 0) + 1
        for held in self.status.held.values():
            day = answer.latest(held.subject.rate_type)
            if day is not None and (held.latest_day is None or day > held.latest_day):
                held.latest_day = day

    def _on_release_day(self, one: Stated, today: date) -> bool:
        day = one.published.day
        if one.subject.rate_type == "SOFRAI":
            return today == day
        return day < today <= day + timedelta(days=RELEASE_DAYS)

    async def record(
        self,
        figures: Sequence[Stated],
        key: str,
        *,
        want_id: str = "",
        seen_ns: int = 0,
    ) -> Outcome:
        """Record `figures`, read from the answer kept at `key`, against
        `want_id` where given; `seen_ns` the moment a rate first seen now
        was seen appear, 0 where the plugin did not see it appear."""
        instruments = await self.resolve()
        today = self.today()

        def first(one: Stated, row_key: str) -> First:
            day = one.published.day
            published = seen_ns if seen_ns and self._on_release_day(one, today) else 0
            where = self.raw.first(row_key, day, str(one.value), key, published)
            if where.key == key and where.published_ns == published and published:
                lag = (published - day_start_ns(day)) // 10**9
                self.status.lags = [*self.status.lags[-(LAGS - 1) :], lag]
            return where

        rows, unresolved = to_rates(self.rates, NYFED_RATES, figures, instruments, first)
        self.raw.save_firsts()
        counts = self.wants.counts
        before = (counts.recorded, counts.restated, counts.unchanged)
        if rows:
            await self.rates.record(NYFED_RATES, rows, want_id)
        restated = counts.restated - before[1]
        self.status.revisions += restated
        return Outcome(
            counts.recorded - before[0], restated, counts.unchanged - before[2], unresolved
        )

    async def check(self) -> Outcome | None:
        """Read the current rates; record them where they state something
        this process has not recorded. None where nothing was recorded."""
        self.status.checked_at = self.now()
        start, end = self.api.current(self.today())
        try:
            answer, fetched = await self.read(start, end)
        except (Unreachable, NotRates) as failed:
            self.status.error = str(failed)
            log.warning("the current rates were not read: %s", failed)
            return None
        self.status.error = ""
        self.status.read_at = self.now()
        seen_from = self._previous_read_ns
        self._previous_read_ns = self.now_ns()
        digest = digest_of(answer)
        if digest != self._current_digest:
            self._current_key = self.raw.keep(fetched)
            self._current_digest = digest
        else:
            self.status.unchanged_reads += 1
        self._current = answer
        self._note(answer)
        if answer.days:
            self.status.first_day, self.status.latest_day = answer.days[0], answer.days[-1]
            for rate_type in {r.rate_type for r in answer.rates}:
                latest = answer.latest(rate_type)
                if latest is not None:
                    self.status.latest_by_type[rate_type] = latest
        await self._alive()
        if digest == self._recorded_digest:
            return None
        recent = seen_from and self._previous_read_ns - seen_from <= SEEN_WITHIN_SECONDS * 10**9
        outcome = await self.record(
            stated(answer.rates),
            self._current_key,
            seen_ns=self._previous_read_ns if recent else 0,
        )
        if not outcome.unresolved:
            self._recorded_digest = digest
        log.info(
            "the rates of %s to %s: %d recorded, %d restated, %d unchanged%s",
            self.status.first_day,
            self.status.latest_day,
            outcome.recorded,
            outcome.restated,
            outcome.unchanged,
            f"; not held: {', '.join(outcome.unresolved)}" if outcome.unresolved else "",
        )
        return outcome

    async def _alive(self) -> None:
        """The dataset's sign of life (contract v27, RecordLiveness): the API
        answered, which confirms every rate in force."""
        try:
            await self.wants.liveness(NYFED_RATES)
        except meridian.MeridianError as refused:
            log.warning("the dataset's liveness was not recorded: %s", refused)

    def next_release(self, rate_type: str) -> date | None:
        """The day the next rate of `rate_type` is expected, Monday to
        Friday: a fixing the business day after its effective date, SOFRAI on
        its own."""
        latest = self.status.latest_by_type.get(rate_type)
        if latest is None:
            return None
        if rate_type == "SOFRAI":
            return next_weekday(latest)
        return next_weekday(next_weekday(latest))

    # ── History ─────────────────────────────────────────────────────────

    def _years(self) -> list[tuple[int, date, date]]:
        """The backfill's years, newest first, each with its first and last day."""
        earliest = self.api.earliest() or EARLIEST
        today = self.today()
        out = []
        for year in range(today.year, earliest.year - 1, -1):
            start = max(date(year, 1, 1), earliest)
            end = min(date(year, 12, 31), today)
            out.append((year, start, end))
        return out

    async def backfill(self, pause: Callable[[], Any] | None = None) -> int:
        """Every rate the NY Fed publishes, a year per request, newest first,
        recorded; each year noted in storage as read, so it is read once. A
        year holding a rate of a record the deployment does not hold is
        recorded for the rest and left unnoted, read again on a later pass
        (`waiting`). How many rows were sent."""
        mode = self.api.mode
        noted = self.raw.backfill(mode)
        done_years = {int(y) for y in noted.get("years", []) if str(y).isdigit()}
        self.status.backfill_years = sorted(done_years)
        self.status.backfill_done = bool(noted.get("done"))
        if self.status.backfill_done:
            return 0
        sent = 0
        waiting: dict[str, None] = {}
        for year, start, end in self._years():
            if year in done_years:
                continue
            try:
                answer, fetched = await self.read(start, end)
            except (Unreachable, NotRates) as failed:
                self.status.backfill_error = f"{year}: {failed}"
                log.warning("the backfill stopped at %d: %s", year, failed)
                return sent
            key = self.raw.keep(fetched)
            self._note(answer)
            outcome = await self.record(stated(answer.rates), key)
            sent += outcome.recorded + outcome.restated + outcome.unchanged
            log.info("the backfill read %d: %d rows", year, len(answer.rates))
            if outcome.unresolved:
                waiting.update(dict.fromkeys(outcome.unresolved))
            else:
                done_years.add(year)
                self.status.backfill_years = sorted(done_years)
                self.raw.note_backfill(mode, sorted(done_years), False)
            if pause is not None:
                await pause()
        if waiting:
            self.status.backfill_error = f"waiting for records not held: {', '.join(waiting)}"
            self.status.backfill_waiting = True
            return sent
        self.status.backfill_error = ""
        self.status.backfill_waiting = False
        self.raw.note_backfill(mode, sorted(done_years), True)
        self.status.backfill_done = True
        return sent

    # ── Wants ───────────────────────────────────────────────────────────

    async def on_want(self, heard: meridian.Heard[ops.ObservationsWantedEvent]) -> None:
        """Record what the lake wants of the plugin's dataset, or decline it
        (the SDK's `Wants.hear`, answered by `answer`)."""
        await self.wants.hear(heard, self.answer)

    async def on_withdrawn(self, heard: meridian.Heard[ops.WantWithdrawnEvent]) -> None:
        """A standing want withdrawn: no longer kept current."""
        self.wants.withdraw(heard.message.want_id)
        log.info("standing want %s withdrawn", heard.message.want_id)

    def _days(self, want: ops.ObservationsWantedEvent) -> list[date]:
        if want.business_date:
            return [date.fromisoformat(want.business_date)]
        start = new_york_day(want.valid_from_ns)
        # Valid times end before `valid_until_ns`: a range to midnight holds
        # no day after it.
        end = new_york_day(want.valid_until_ns - 1 if want.valid_until_ns else self.now_ns())
        days = [start + timedelta(days=n) for n in range((end - start).days + 1)]
        return days[-MOST_DAYS:]

    async def answer(
        self,
        want: ops.ObservationsWantedEvent,
        key: str,
        subjects: list[str],
        kinds: tuple[int, ...],
    ) -> dict[str, str]:
        """One want answered from the API: its rates recorded against it,
        and each subject declined, with why."""
        if key != NYFED_RATES or want.data_type not in ("", RATE):
            return {s: "not_covered" for s in subjects}
        await self.resolve()
        held = {h.instrument_id: h.subject for h in self.status.held.values() if h.instrument_id}
        declined = {s: "not_covered" for s in subjects if s not in held}
        covered = [s for s in subjects if s in held]
        if not covered:
            return declined
        if want.standing:
            self.wants.stand(want, covered, kinds)
        if not want.business_date and not want.valid_from_ns:
            declined.update(await self._record_latest(want, covered, held))
        else:
            declined.update(await self._record_days(want, self._days(want), covered, held))
        return declined

    async def _record_latest(
        self, want: ops.ObservationsWantedEvent, covered: list[str], held: dict[str, Subject]
    ) -> dict[str, str]:
        """The latest rate of each subject wanted, from the current rates."""
        if self._current is None:
            await self.check()
        if self._current is None:
            return {s: "source_silent" for s in covered}
        codes = {held[s].code for s in covered}
        figures = [f for f in stated(self._current.rates) if f.subject.code in codes]
        latest = {
            code: max((f.published.day for f in figures if f.subject.code == code), default=None)
            for code in codes
        }
        chosen = [f for f in figures if f.published.day == latest[f.subject.code]]
        await self.record(chosen, self._current_key, want_id=want.want_id)
        return {s: "source_silent" for s in covered if latest[held[s].code] is None}

    async def _record_days(
        self,
        want: ops.ObservationsWantedEvent,
        days: list[date],
        covered: list[str],
        held: dict[str, Subject],
    ) -> dict[str, str]:
        """Record the days asked against the want; each subject declined,
        with why, where it has no rate on them."""
        today = self.today()
        if days and all(d < EARLIEST for d in days):
            return {s: "beyond_history" for s in covered}
        open_days = [d for d in days if EARLIEST <= d <= today and d.weekday() < 5]
        if not open_days:
            return {s: "source_silent" for s in covered}
        try:
            answer, fetched = await self.read(min(open_days), max(open_days))
        except (Unreachable, NotRates) as failed:
            log.warning("want %s: the API was not read: %s", want.want_id, failed)
            return {s: "source_silent" for s in covered}
        codes = {held[s].code for s in covered}
        figures = [f for f in stated(answer.rates, open_days) if f.subject.code in codes]
        if figures:
            key = self.raw.keep(fetched)
            self._note(answer)
            await self.record(figures, key, want_id=want.want_id)
        stated_codes = {f.subject.code for f in figures}
        return {s: "source_silent" for s in covered if held[s].code not in stated_codes}


def digest_of(answer: Answer) -> str:
    """What an answer states, as a short digest: its rates, never the
    answer's other bytes."""
    said = repr(
        [
            (r.rate_type, r.day, sorted(r.values.items()), sorted(r.percentiles.items()),
             r.volume_billions, r.revised)
            for r in answer.rates
        ]
    ).encode()  # fmt: skip
    return hashlib.sha256(said).hexdigest()[:16]
