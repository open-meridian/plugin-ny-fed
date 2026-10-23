"""The NY Fed's rates into the lake: read, resolved, converted through the
SDK's rates helpers, recorded once, revised as the next version, published
when seen appear, backfilled once, and wanted."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from meridian.operations import as_decimal
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles.data import rates

from ny_fed.api import Fetched, LiveApi, SyntheticApi, Unreachable
from ny_fed.feed import day_start_ns

from conftest import CODES, ET_0805, SOFR, Appearing, Clock, Revised, feed, lake, want


def rows(plugin: Any, batch: int | None = None) -> list[Any]:
    sent = plugin.on("RecordRates")
    chosen = sent if batch is None else [sent[batch]]
    return [r for b in chosen for r in b.rates]


def by_key(found: list[Any], code: str, day: str, kind: str = "fixing") -> Any:
    instrument = "INS-" + "".join(c for c in code.upper() if c.isalnum())
    [one] = [
        r for r in found
        if r.meta.row_key.startswith(f"nyfed:{kind}:")
        and r.meta.business_date == day and r.meta.row_key.endswith("@" + instrument)
    ]  # fmt: skip
    return one


async def test_the_current_rates_recorded_as_rates(tmp_path: Path) -> None:
    plugin = lake()
    work = feed(tmp_path, plugin)
    outcome = await work.check()
    assert outcome is not None and outcome.unresolved == ()
    found = rows(plugin)
    # 13 to 23 October: eight fixing days of five rates, nine of SOFRAI's four.
    assert len(found) == 8 * 5 + 9 * 4 == outcome.recorded
    sofr = by_key(found, "SOFR", "2026-10-22")
    assert sofr.kind == ops.RATE_KIND_FIXING
    assert (
        as_decimal(sofr.value.value) == Decimal("3.90")
        and sofr.value.unit == ops.VALUE_UNIT_PERCENT
    )
    assert sofr.convention.day_count == ops.DAY_COUNT_ACT_360
    assert sofr.convention.compounding == ops.COMPOUNDING_SIMPLE
    assert {p.percentile: str(as_decimal(p.value)) for p in sofr.percentiles} == {
        1: "3.83",
        25: "3.88",
        75: "3.95",
        99: "3.98",
    }
    assert as_decimal(sofr.volume.amount) == 2_945_000_000_000
    assert sofr.volume.currency_code == "USD"
    assert not sofr.HasField("tenor") and not sofr.preliminary
    assert sofr.meta.valid_from_ns == day_start_ns(date(2026, 10, 22))
    assert sofr.meta.subjects[0].entity_id == SOFR
    assert sofr.meta.source.dataset == "ny-fed:nyfed_rates"
    assert sofr.meta.raw.key.startswith("responses/2026-10/")
    # First read after a start: not seen appear, so no published time.
    assert list(sofr.meta.source_times) == []
    index = by_key(found, "SOFR Index", "2026-10-23", "index_level")
    assert index.value.unit == ops.VALUE_UNIT_INDEX
    assert str(as_decimal(index.value.value)) == "1.26398658"
    assert index.value.index_base == "2018-04-02=1.00000000"
    assert not index.HasField("convention")
    average = by_key(found, "SOFR 90-day average", "2026-10-23", "average")
    assert str(as_decimal(average.value.value)) == "3.75301"
    assert average.convention.day_count == ops.DAY_COUNT_ACT_360
    assert work.status.held["SOFR"].latest_day == date(2026, 10, 22)
    assert work.status.held["SOFR Index"].latest_day == date(2026, 10, 23)


async def test_a_rate_never_passes_through_a_float(tmp_path: Path) -> None:
    """`an-exact-price`'s question asked of rates: every figure as stated."""
    plugin = lake()
    await feed(tmp_path, plugin).check()
    said = {str(as_decimal(r.value.value)) for r in rows(plugin)}
    assert "3.90" in said and "1.26398658" in said
    assert all("e" not in s.lower() for s in said)


async def test_the_same_answer_records_nothing_twice(tmp_path: Path) -> None:
    plugin = lake()
    clock = Clock()
    work = feed(tmp_path, plugin, clock)
    await work.check()
    clock.move(minutes=5)
    assert await work.check() is None
    assert len(plugin.on("RecordRates")) == 1
    assert len(work.raw.keys()) == 1, "an answer stating nothing new is not kept again"
    assert work.status.unchanged_reads == 1
    # Each answer is the dataset's sign of life.
    assert [len(b.liveness) for b in plugin.on("RecordLiveness")] == [1, 1]
    # A new process, the same storage: every rate answered unchanged, naming
    # the answer it was first read from.
    again = lake()
    later = feed(tmp_path, again, clock)
    outcome = await later.check()
    assert outcome is not None and outcome.recorded == 76 and outcome.unchanged == 0
    first = {r.meta.row_key: r.meta.raw.key for r in rows(plugin)}
    assert {r.meta.row_key: r.meta.raw.key for r in rows(again)} == first


async def test_a_revision_is_the_next_version_published_later(tmp_path: Path) -> None:
    plugin = lake()
    clock = Clock(datetime(2026, 10, 23, 18, 20, tzinfo=UTC))  # 14:20 ET
    work = feed(tmp_path, plugin, clock, Revised(clock))
    await work.check()
    clock.move(minutes=10)  # 14:30 ET: the NY Fed revises SOFR of 22 October
    outcome = await work.check()
    assert outcome is not None and (outcome.recorded, outcome.restated) == (0, 1)
    before = by_key(rows(plugin, 0), "SOFR", "2026-10-22")
    after = by_key(rows(plugin, 1), "SOFR", "2026-10-22")
    assert before.meta.row_key == after.meta.row_key
    assert as_decimal(after.value.value) == Decimal("3.92")
    assert plugin.versions[("rate", after.meta.row_key)][0] == 2
    # The revision seen appear on its day of publication: published then.
    [published] = after.meta.source_times
    assert published.kind == ops.SOURCE_TIME_KIND_PUBLISHED
    assert published.at_ns == int(clock.at.timestamp()) * 10**9
    assert after.meta.raw.key != before.meta.raw.key
    assert work.status.revisions == 1


async def test_a_rate_seen_appear_is_published_then(tmp_path: Path) -> None:
    plugin = lake()
    clock = Clock(datetime(2026, 10, 23, 12, 0, tzinfo=UTC))  # 08:00 ET
    work = feed(tmp_path, plugin, clock, Appearing(clock))
    await work.check()
    assert all(not r.meta.source_times for r in rows(plugin, 0))
    clock.at = ET_0805
    outcome = await work.check()
    assert outcome is not None and outcome.recorded == 5 + 4
    fresh = rows(plugin, 1)
    seen = [r for r in fresh if r.meta.source_times]
    assert len(seen) == 9
    assert {r.meta.source_times[0].at_ns for r in seen} == {int(ET_0805.timestamp()) * 10**9}
    # Every other rate was read before, and keeps its first answer.
    assert all(not r.meta.source_times for r in fresh if r not in seen)
    # SOFRAI of 23 October, seen 08:05 ET that day: 8 h 05 m after its day
    # began; SOFR of 22 October, seen then too: 32 h 05 m.
    assert sorted(set(work.status.lags)) == [8 * 3600 + 5 * 60, 32 * 3600 + 5 * 60]


async def test_a_rate_first_read_long_after_states_no_published_time(tmp_path: Path) -> None:
    plugin = lake()
    clock = Clock(datetime(2026, 10, 23, 12, 0, tzinfo=UTC))
    work = feed(tmp_path, plugin, clock, Appearing(clock))
    await work.check()
    clock.at = datetime(2026, 10, 23, 14, 0, tzinfo=UTC)  # two hours on: not seen appear
    await work.check()
    assert all(not r.meta.source_times for r in rows(plugin))


async def test_a_record_not_held_is_reported_and_its_rates_wait(tmp_path: Path) -> None:
    plugin = lake(missing="SOFR 180-day average")
    work = feed(tmp_path, plugin)
    outcome = await work.check()
    assert outcome is not None and outcome.unresolved == ("SOFR 180-day average",)
    [miss] = plugin.on("ReportMissingInstrument")
    assert miss.identifiers[0].value == "SOFR 180-day average"
    assert miss.identifiers[0].source == "nyfed" and miss.reason == ops.MISS_REASON_NOT_FOUND
    assert len(rows(plugin)) == 76 - 9
    assert work.status.held["SOFR 180-day average"].miss == "not_found"
    # Read again: the miss is not reported twice the same day, and the rates
    # held are not sent again.
    await work.check()
    assert len(plugin.on("ReportMissingInstrument")) == 1


async def test_two_records_meeting_a_symbol_are_ambiguous(tmp_path: Path) -> None:
    plugin = lake(ambiguous="EFFR")
    work = feed(tmp_path, plugin)
    await work.check()
    [miss] = plugin.on("ReportMissingInstrument")
    assert miss.reason == ops.MISS_REASON_AMBIGUOUS
    assert work.status.held["EFFR"].miss == "ambiguous"


async def test_the_api_not_reached(tmp_path: Path) -> None:
    class Down(SyntheticApi):
        async def get(self, path: str) -> Fetched:
            raise Unreachable("https://markets.newyorkfed.org: ConnectionRefusedError")

    plugin = lake()
    work = feed(tmp_path, plugin, api=Down(Clock()))
    assert await work.check() is None
    assert "ConnectionRefusedError" in work.status.error
    assert plugin.on("RecordRates") == [] and plugin.on("RecordLiveness") == []


async def test_the_history_backfilled_once(tmp_path: Path) -> None:
    plugin = lake()
    work = feed(tmp_path, plugin)
    sent = await work.backfill()
    # Sample data's history: the recording from 3 August, 57 fixing days of
    # five rates and 58 of SOFRAI's four.
    assert sent == 57 * 5 + 58 * 4
    assert work.status.backfill_done and work.status.backfill_years == [2026]
    assert work.raw.backfill("synthetic") == {"years": [2026], "done": True}
    again = feed(tmp_path, lake())
    assert await again.backfill() == 0 and again.status.backfill_done
    # Backfilled rates were not seen appear: no published time.
    assert all(not r.meta.source_times for r in rows(plugin))


def test_the_live_history_is_read_a_year_at_a_time_newest_first(tmp_path: Path) -> None:
    work = feed(tmp_path, api=LiveApi(Clock()))
    years = work._years()
    assert years[0] == (2026, date(2026, 1, 1), date(2026, 10, 23))
    assert years[-1] == (2000, date(2000, 7, 3), date(2000, 12, 31))
    assert len(years) == 27


async def test_a_backfill_waiting_for_a_record_goes_on_and_is_read_again(tmp_path: Path) -> None:
    work = feed(tmp_path, lake(missing="SOFR Index"))
    await work.backfill()
    assert not work.status.backfill_done and work.status.backfill_waiting
    assert "SOFR Index" in work.status.backfill_error
    assert work.raw.backfill("synthetic")["done"] is False
    held = feed(tmp_path, lake())
    await held.backfill()
    assert held.status.backfill_done


async def test_a_want_recorded_against(tmp_path: Path) -> None:
    """`a-want-recorded-against`'s question asked of rates."""
    plugin = lake()
    work = feed(tmp_path, plugin)
    await work.on_want(want("w-0925", [SOFR], day="2026-09-25"))
    [sent] = plugin.on("RecordRates")
    assert sent.want_id == "w-0925"
    [one] = sent.rates
    assert one.meta.business_date == "2026-09-25" and one.meta.subjects[0].entity_id == SOFR
    assert plugin.on("DeclineWant") == []


async def test_a_range_wanted_for_two_records(tmp_path: Path) -> None:
    plugin = lake()
    work = feed(tmp_path, plugin)
    index = "INS-SOFRINDEX"
    start = day_start_ns(date(2026, 9, 21))
    until = day_start_ns(date(2026, 9, 26))
    await work.on_want(want("w-week", [SOFR, index], valid_from_ns=start, valid_until_ns=until))
    [sent] = plugin.on("RecordRates")
    assert sorted({r.meta.business_date for r in sent.rates}) == [
        "2026-09-21",
        "2026-09-22",
        "2026-09-23",
        "2026-09-24",
        "2026-09-25",
    ]
    assert len(sent.rates) == 10


async def test_what_the_nyfed_never_states_is_declined(tmp_path: Path) -> None:
    plugin = lake()
    work = feed(tmp_path, plugin)
    asked = len(work.api.asked)  # type: ignore[attr-defined]
    await work.on_want(want("w-sat", [SOFR], day="2026-10-17"))
    await work.on_want(want("w-1999", [SOFR], day="1999-12-31"))
    await work.on_want(want("w-price", [SOFR], day="2026-10-16", data_type="meridian.v1.Price"))
    await work.on_want(want("w-other", ["INS-ELSE"], day="2026-10-16"))
    reasons = {d.want_id: d.reason for d in plugin.on("DeclineWant")}
    assert reasons == {
        "w-sat": ops.UNANSWERED_REASON_SOURCE_SILENT,
        "w-1999": ops.UNANSWERED_REASON_BEYOND_HISTORY,
        "w-price": ops.UNANSWERED_REASON_NOT_COVERED,
        "w-other": ops.UNANSWERED_REASON_NOT_COVERED,
    }
    assert len(work.api.asked) == asked, "nothing asked of the API"  # type: ignore[attr-defined]


async def test_a_holiday_asked_is_source_silent(tmp_path: Path) -> None:
    plugin = lake()
    work = feed(tmp_path, plugin)
    # Columbus Day, 12 October 2026: the NY Fed publishes no rate for it.
    await work.on_want(want("w-holiday", [SOFR], day="2026-10-12"))
    [declined] = plugin.on("DeclineWant")
    assert declined.reason == ops.UNANSWERED_REASON_SOURCE_SILENT
    assert plugin.on("RecordRates") == []


async def test_the_latest_and_a_standing_want(tmp_path: Path) -> None:
    plugin = lake()
    work = feed(tmp_path, plugin)
    await work.on_want(want("w-latest", [SOFR, "INS-SOFRINDEX"], standing=True))
    sent = [b for b in plugin.on("RecordRates") if b.want_id == "w-latest"]
    assert [sorted(r.meta.business_date for r in b.rates) for b in sent] == [
        ["2026-10-22", "2026-10-23"]
    ]
    assert "w-latest" in work.wants.standing
    work.wants.withdraw("w-latest")
    assert work.wants.standing == {}


def test_every_record_named_by_its_seeded_symbol() -> None:
    from ny_fed.declared import SUBJECTS

    assert [s.code for s in SUBJECTS] == CODES
    assert {s.instrument_type for s in SUBJECTS} == {"interest_rate", "index"}
    assert rates.MONEY_MARKET.day_count == "act_360"
