"""The Federal Reserve Bank of New York's reference rates as an Open
Meridian data plugin (spec/a-public-rates-and-filings-data-plugin,
"plugin-ny-fed"; one plugin per publisher's feed, rulings 343 to 349): SOFR,
EFFR, OBFR, TGCR and BGCR, each a daily fixing with its percentiles and
volume, the SOFR 30, 90 and 180-day averages, and the SOFR Index, into the
deployment's lake as rates (contract v27).

It runs its data role class, `Lake` (feed.py's `Feed`, with its lifecycle
here), with `meridian.run` on the sidecar it is launched beside, declaring
its catalogue, its storage and its one setting (declaration.py);
`meridian.run` delivers the settings, serves its two pages (page.py), hands
it what the lake wants of it, and sets the data role's figures on each
heartbeat. It reads the NY Fed's current rates at start and then at the
publication windows (schedule.py), recording what it has not recorded in
this process, and backfills the NY Fed's history once (feed.py). What the
API answered is kept in the storage the deployment grants (raw.py), and
moved past its window as the settings say. It reads which of its datasets a
deployment admin has licensed, on start and every minute. It holds nothing
else: a restart reads the API again, and the lake answers what it recorded
before unchanged; it does not stream.

Everything it says to the deployment goes through the sidecar; everything it
reads comes from the NY Fed's public markets data API, or with sample data
from the answer committed with it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

import meridian

from . import schedule
from .api import SPACING, api
from .declaration import DECLARATION, PORT
from .feed import Feed
from .page import figures, hold, pages
from .raw import RawStore
from .settings import Config, config_from

log = logging.getLogger("ny_fed")

#: How often storage is tended past its window, in seconds: daily.
TEND_SECONDS = 86_400
#: How often the datasets' licences are read again.
LICENCES_SECONDS = 60
#: How long the backfill waits after a stop before trying again: an hour, or
#: a day where it waits for a record the deployment does not hold, which the
#: SDK reports missing once a day.
BACKFILL_RETRY_SECONDS = 3600
BACKFILL_WAITING_SECONDS = 86_400


class Lake(Feed):
    """The data role's class with its lifecycle (open-meridian 0.35, rulings
    1004, 1005, 1009 to 1023): `meridian.run` delivers each settings to
    `on_settings` -- the first before anything is heard -- and starts `run`,
    again after a backoff should it fail."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.config = Config()
        self.wake = asyncio.Event()
        self.read_once = asyncio.Event()

    async def on_settings(self, delivered: Any) -> None:
        """Apply each delivery of the settings: sample data on or off, and the
        answers' window, tended at once."""
        config = config_from(delivered.values)
        self.config = config
        self.use(api(config.sample_data))
        self.wake.set()
        await self.raw.tend(self.plugin, config.window_days, config.past_window, self.now())

    async def run(self) -> None:
        """The current rates read, the history backfilled, storage tended,
        the licences read, and the feed delay reported (contract v28,
        ReportLatency)."""
        await asyncio.gather(
            self._check(), self._backfill(), self._tend(), self._licences(), self.latency.run()
        )

    async def _check(self) -> None:
        """Read the current rates at once, then as the schedule says, or at
        once when the settings change."""
        while True:
            self.wake.clear()
            try:
                await self.check()
            except meridian.MeridianError as failed:
                # The sidecar refused something a recording needed; say so and
                # keep the schedule rather than spin.
                self.status.error = f"the deployment refused a recording: {failed}"
                log.warning("this check stopped: %s", failed)
            if self.status.read_at is not None:
                self.read_once.set()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.wake.wait(), timeout=schedule.next_read_in(self.now()))

    async def _backfill(self) -> None:
        """The NY Fed's history, once, after the first read of the current
        rates; looked at again hourly, so one that stopped goes on where it
        did, and sample data turned on or off is backfilled from its own
        source (its progress noted by mode); daily while it waits for a
        record the deployment does not hold."""
        await self.read_once.wait()
        while True:
            try:
                await self.backfill(pause=lambda: asyncio.sleep(SPACING))
            except meridian.MeridianError as failed:
                self.status.backfill_error = f"the deployment refused a recording: {failed}"
                log.warning("the backfill stopped: %s", failed)
            waiting = self.status.backfill_waiting
            await asyncio.sleep(BACKFILL_WAITING_SECONDS if waiting else BACKFILL_RETRY_SECONDS)

    async def _tend(self) -> None:
        while True:
            await asyncio.sleep(TEND_SECONDS)
            config = self.config
            await self.raw.tend(self.plugin, config.window_days, config.past_window, self.now())

    async def _licences(self) -> None:
        """Its own declared dataset's licence (contract v20, W10.9), read on
        start and every minute, for the Datasets page."""
        while True:
            try:
                await self.wants.read_licences()
            except meridian.MeridianError as failed:
                log.warning("the dataset's licence was not read this time: %s", failed)
            await asyncio.sleep(LICENCES_SECONDS)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    lake = Lake(api(False), RawStore())
    hold(lake)
    # The version's whole declaration (declaration.py): its settings, its
    # pages with the levels each serves and their tools, and its
    # documentation. A version registers exactly what it was uploaded with
    # (contract v25).
    meridian.run(
        declaration=DECLARATION,
        roles=[lake],
        pages=pages,
        port=PORT,
        on_settings=lake.on_settings,
        figures=lambda: figures(lake.status, lake),
    )


if __name__ == "__main__":
    main()
