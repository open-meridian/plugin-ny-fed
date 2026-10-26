"""The Federal Reserve Bank of New York's reference rates as an Open
Meridian data plugin (spec/a-public-rates-and-filings-data-plugin,
"plugin-ny-fed"; one plugin per publisher's feed, rulings 343 to 349): SOFR,
EFFR, OBFR, TGCR and BGCR, each a daily fixing with its percentiles and
volume, the SOFR 30, 90 and 180-day averages, and the SOFR Index, into the
deployment's lake as rates (contract v27).

It connects to the sidecar it is launched beside with its catalogue, its
storage and its one setting (declaration.py), serves its two pages
(page.py), hears what the lake wants of it, reads the NY Fed's current rates
at start and then at the publication windows (schedule.py), recording what
it has not recorded in this process, and backfills the NY Fed's history once
(feed.py). What the API answered is kept in the storage the deployment
grants (raw.py), and moved past its window as the settings say. It reads
which of its datasets a deployment admin has licensed, on start and every
minute, and reports the data role's figures on its heartbeat. It holds
nothing else: a restart reads the API again, and the lake answers what it
recorded before unchanged; it does not stream.

Everything it says to the deployment goes through the sidecar; everything it
reads comes from the NY Fed's public markets data API, or with sample data
from the answer committed with it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

import meridian

from . import schedule
from .api import SPACING, api
from .declaration import DECLARATION, PORT
from .feed import Feed
from .page import figures, hold, pages
from .raw import RawStore
from .settings import Config, config_from

log = logging.getLogger("ny_fed")

#: How long before a broken settings stream is asked again, in seconds.
RETRY_SECONDS = 5
#: How often storage is tended past its window, in seconds: daily.
TEND_SECONDS = 86_400
#: How often the datasets' licences are read again, and the figures set.
LICENCES_SECONDS = 60
#: How long the backfill waits after a stop before trying again: an hour, or
#: a day where it waits for a record the deployment does not hold, which the
#: SDK reports missing once a day.
BACKFILL_RETRY_SECONDS = 3600
BACKFILL_WAITING_SECONDS = 86_400


async def watch_settings(
    plugin: meridian.Plugin, feed: Feed, held: list[Config], wake: asyncio.Event
) -> None:
    """Apply each delivery of the settings: sample data on or off, and the
    answers' window, tended at once. A stream that breaks -- the deployment
    not serving its configuration yet at a first start, or restarting -- is
    asked again after a pause, and delivers the settings whole."""
    while True:
        try:
            async for delivered in plugin.settings():
                config = config_from(delivered.values)
                held[0] = config
                feed.use(api(config.sample_data))
                wake.set()
                await feed.raw.tend(plugin, config.window_days, config.past_window, feed.now())
        except Exception as broken:  # noqa: BLE001 - a broken stream, asked again
            log.warning("the settings were not delivered (%s); asking again", broken)
        await asyncio.sleep(RETRY_SECONDS)


async def check(feed: Feed, wake: asyncio.Event, read_once: asyncio.Event) -> None:
    """Read the current rates once the settings have come, then as the
    schedule says, or at once when the settings change."""
    await wake.wait()
    while True:
        wake.clear()
        try:
            await feed.check()
        except meridian.MeridianError as failed:
            # The sidecar refused something a recording needed; say so and
            # keep the schedule rather than spin.
            feed.status.error = f"the deployment refused a recording: {failed}"
            log.warning("this check stopped: %s", failed)
        if feed.status.read_at is not None:
            read_once.set()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(wake.wait(), timeout=schedule.next_read_in(feed.now()))


async def backfill(feed: Feed, read_once: asyncio.Event) -> None:
    """The NY Fed's history, once, after the first read of the current
    rates; looked at again hourly, so one that stopped goes on where it
    did, and sample data turned on or off is backfilled from its own
    source (its progress noted by mode); daily while it waits for a record
    the deployment does not hold."""
    await read_once.wait()
    while True:
        try:
            await feed.backfill(pause=lambda: asyncio.sleep(SPACING))
        except meridian.MeridianError as failed:
            feed.status.backfill_error = f"the deployment refused a recording: {failed}"
            log.warning("the backfill stopped: %s", failed)
        waiting = feed.status.backfill_waiting
        await asyncio.sleep(BACKFILL_WAITING_SECONDS if waiting else BACKFILL_RETRY_SECONDS)


async def tend(plugin: meridian.Plugin, feed: Feed, held: list[Config]) -> None:
    while True:
        await asyncio.sleep(TEND_SECONDS)
        config = held[0]
        await feed.raw.tend(plugin, config.window_days, config.past_window, feed.now())


async def licences(plugin: meridian.Plugin, feed: Feed) -> None:
    """Its own declared dataset's licence (contract v20, W10.9), read on
    start and every minute, for the Datasets page; and the data role's
    figures, set for the next heartbeat."""
    while True:
        try:
            await feed.wants.read_licences()
        except meridian.MeridianError as failed:
            log.warning("the dataset's licence was not read this time: %s", failed)
        plugin.figures = figures(feed.status, feed)
        await asyncio.sleep(LICENCES_SECONDS)


def _said(task: asyncio.Task[None]) -> None:
    """A task that ended on an error says so, rather than ending unseen."""
    if not task.cancelled() and task.exception() is not None:
        log.error("%s stopped", task.get_name(), exc_info=task.exception())


async def run() -> None:
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for stop in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(stop, stopped.set)

    # The version's whole declaration (declaration.py): its settings, its
    # pages with the levels each serves and their tools, and its documentation.
    # A version registers exactly what it was uploaded with (contract v25).
    async with await meridian.connect(declaration=DECLARATION) as plugin:
        log.info("registered as %s, roles %s", plugin.identity.instance_id, plugin.identity.roles)
        feed = Feed(plugin, api(False), RawStore())
        hold(feed)
        held = [Config()]
        wake = asyncio.Event()
        read_once = asyncio.Event()
        server = pages.serve(plugin, PORT)
        log.info("serving its pages on 127.0.0.1:%d", PORT)
        tasks = [
            asyncio.create_task(
                plugin.receive(observations_wanted=feed.on_want, want_withdrawn=feed.on_withdrawn)
            ),
            asyncio.create_task(watch_settings(plugin, feed, held, wake)),
            asyncio.create_task(check(feed, wake, read_once)),
            asyncio.create_task(backfill(feed, read_once)),
            asyncio.create_task(tend(plugin, feed, held)),
            asyncio.create_task(licences(plugin, feed)),
            # Contract v28: the feed delay, reported (ReportLatency).
            asyncio.create_task(feed.latency.run()),
        ]
        for task in tasks:
            task.add_done_callback(_said)
        await stopped.wait()
        log.info("stopping")
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        server.shutdown()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(run())


if __name__ == "__main__":
    main()
