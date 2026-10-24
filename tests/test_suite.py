"""The data suite (meridian.suites) at contract v27, each case the NY Fed's
reference rates present mapped to the plugin's own conversion of the NY
Fed's recorded answer: the rates slice's cases as
spec/a-public-rates-and-filings-data-plugin §6 lists them, as far as the NY
Fed publishes them.

The NY Fed publishes reference rates: five daily fixings with their
percentiles and volume, three averages and an index, each its own record.
What a rates-only plugin never presents -- every case about a price, a trade,
a quote or an outcome, `an-exact-price` and `a-want-recorded-against` about
closes from ruling 537, and the feed delay, about latency until contract v28
(ruling 518) -- is the SDK's `RATES_NOT_PRESENTED` (ruling 538), with its
reasons; from 0.32.2 it leaves liveness to each plugin. Not presented besides, each with its reason:

- the rates slice's curve cases -- a curve for a date, a tenor not
  published, a bill's two conventions and another source's curve point --
  since the NY Fed publishes no curve, no tenor and no bill;
- `reads-a-calendar`: the dataset declares no calendar (the spec's Q15: the
  US government securities calendar is curated on a miss, and none is held
  yet); the plugin takes Monday to Friday and reads none;
- `asks-for-a-settlement-date`: it records rates as published.

`records-a-datasets-liveness` is presented: each answer of the API is the
dataset's sign of life (RecordLiveness), which confirms the rates in force,
a poll as the SDK's `Wants.liveness` has it. What `an-exact-price` and `a-want-recorded-against`
ask of a rates plugin is held by test_feed.py: a rate never passes through a
float, and a want's rates are recorded against it. The cases every suite
holds that the SDK answers (a replacement, the template catalogue, an event
group heard) are the SDK's.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles.data.testing import RATES_NOT_PRESENTED, Lake
from meridian.suites import ANSWERED_BY_SDK, Recorder, run

from conftest import DATASET, SOFR, Clock, Revised, feed, lake, resolver, want

#: The rates slice's cases about curves, which the NY Fed never publishes.
CURVES = {
    "a-curve-for-a-date": "the NY Fed publishes no curve: each reference rate is its own record",
    "a-tenor-not-published": "the NY Fed publishes no curve, so no tenor goes unpublished",
    "two-conventions-one-tenor": "the NY Fed publishes no bill: one convention for each rate",
    "a-curve-point-from-another-source": "the NY Fed publishes each reference rate itself; "
    "none is another source's curve point",
}
NOT_PRESENTED = {
    **RATES_NOT_PRESENTED,
    **CURVES,
    "reads-a-calendar": "the dataset declares no calendar until the US government securities "
    "calendar is curated (FDP Q15); the plugin takes Monday to Friday and reads none",
    "asks-for-a-settlement-date": "it records rates as published; never a settlement date",
}


def producers(tmp: Path) -> dict[str, Callable[[Recorder], Awaitable[None]]]:
    def store(recorder: Recorder, **kw: Any) -> Recorder:
        """The recorder answering as the deployment's store does, as `lake` does."""
        recorder.answer("ResolveIdentifier", resolver(**kw))
        return recorder

    async def the_rates_read(recorder: Recorder) -> None:
        await feed(tmp / "read", store(recorder)).check()

    async def revised(recorder: Recorder) -> None:
        clock = Clock()
        work = feed(tmp / "revised", store(recorder), clock, Revised(clock))
        await work.check()
        clock.move(minutes=5)
        await work.check()
        sent = recorder.on("RecordRates")
        assert len(sent) == 2

    async def two_records(recorder: Recorder) -> None:
        await feed(tmp / "two", store(recorder, ambiguous="SOFR")).check()

    def wanted(message: Any) -> Callable[[Recorder], Awaitable[None]]:
        async def produce(recorder: Recorder) -> None:
            work = feed(tmp / "wanted", store(recorder))
            recorder.answer("ObservationsWanted", lambda _: message)
            await recorder.receive(observations_wanted=work.on_want)

        return produce

    async def licences(recorder: Recorder) -> None:
        # On start and every minute, its own declared dataset's licence.
        recorder.answer(
            "ListDatasets",
            lambda _: ops.ListDatasetsResult(licences=[ops.DatasetLicence(dataset=DATASET)]),
        )
        work = feed(tmp / "licences", store(recorder))
        await work.wants.read_licences()
        assert work.wants.licensed == {DATASET}

    async def withdrawn(recorder: Recorder) -> None:
        work = feed(tmp / "withdrawn", store(recorder))
        recorder.answer(
            "WantWithdrawn",
            lambda _: ops.WantWithdrawnEvent(want_id="w-standing", dataset=DATASET),
        )
        await recorder.receive(want_withdrawn=work.on_withdrawn)

    async def alive(recorder: Recorder) -> None:
        # The API answering, a check stating nothing new: still a sign of life.
        clock = Clock()
        work = feed(tmp / "alive", store(recorder), clock)
        await work.check()
        clock.move(minutes=5)
        assert await work.check() is None

    return {
        "a-rate-fixing": the_rates_read,
        "a-same-day-revision": revised,
        "an-index-level": the_rates_read,
        "an-asset-that-does-not-resolve": two_records,
        "a-subject-declined": wanted(
            want("w-2", ["INS-NOT-THE-NY-FEDS"], day="2026-10-02").message
        ),
        "a-standing-want-withdrawn": withdrawn,
        "reads-its-datasets-licences": licences,
        "records-a-datasets-liveness": alive,
    }


def test_the_data_suite_passes(tmp_path: Path) -> None:
    report = run("data", producers(tmp_path), not_presented=NOT_PRESENTED, instance_id="ny-fed")
    assert report.passed, report.failures
    assert sorted(report.not_presented) == sorted(NOT_PRESENTED)
    # The plugin's own eight, and the cases every suite holds that the SDK
    # answers (contract v24's two, v26's event group).
    assert len(report.passed_cases) == 8 + len(ANSWERED_BY_SDK)
    assert report.answered_by_sdk == list(ANSWERED_BY_SDK)


def test_a_revision_is_the_rows_next_version(tmp_path: Path) -> None:
    import asyncio

    plugin = lake()
    clock = Clock()
    work = feed(tmp_path, plugin, clock, Revised(clock))
    asyncio.run(work.check())
    clock.move(minutes=5)
    outcome = asyncio.run(work.check())
    assert outcome is not None and outcome.restated == 1 and outcome.recorded == 0
    first, second = ({r.meta.row_key: r for r in batch.rates} for batch in plugin.on("RecordRates"))
    keys = [
        k for k in first if k.startswith("nyfed:fixing") and "2026-10-22" in k and k.endswith(SOFR)
    ]
    assert len(keys) == 1
    assert plugin.versions[("rate", keys[0])][0] == 2
    assert isinstance(plugin, Lake)
