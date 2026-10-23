"""The pages on sample data, each printed as one HTML file:
for looking at them without a deployment.

    python -m ny_fed.preview connection > preview/connection.html
    python -m ny_fed.preview datasets > preview/datasets.html

The plugin's work runs on the SDK's lake as a test stands it in (`Lake`), in
place of a sidecar --
every record resolved to an instrument named for it but the 180-day
average, which the deployment does not hold, every batch recorded --
against the answer committed under responses/, at 16:45 UTC on 23 October
2026: the current rates read, the history backfilled, a want for SOFR on
25 September answered, one for Saturday 17 October declined (the NY Fed
publishes nothing on a weekend), and a standing want kept current. Each page
links the kit where the dashboard serves it, /.meridian/ui/<version>/:
served beside the kit it is styled (`make preview SHOTS=...` checks each in
a browser); opened on its own it is the page without the kit, unstyled,
which works too. `connection-first` and `datasets-first` are the pages
before the first check, with no want yet: the role's "not set up yet"
states.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.receive import Heard
from meridian.roles.data.testing import Lake
from meridian.testing import PageClient

from .api import SyntheticApi
from .feed import Feed
from .page import CONNECTION, DATASETS, hold, pages
from .raw import RawStore

AT = datetime(2026, 10, 23, 16, 45, tzinfo=UTC)
PAGES = {
    "connection": CONNECTION,
    "datasets": DATASETS,
    "connection-first": CONNECTION,
    "datasets-first": DATASETS,
}
#: The record the preview's deployment does not hold, to show a miss.
NOT_HELD = "SOFR 180-day average"


def instrument_of(code: str) -> str:
    """A stand-in record's ID for a code: `INS-` and the code, as a test names it."""
    return "INS-" + "".join(c for c in code.upper() if c.isalnum())


def _want(want_id: str, subject: str, day: str = "", standing: bool = False) -> Heard:  # type: ignore[type-arg]
    return Heard(
        row="ObservationsWanted",
        message=ops.ObservationsWantedEvent(
            want_id=want_id,
            dataset="ny-fed:nyfed_rates",
            data_type="meridian.v1.Rate",
            subjects=[ops.SubjectRef(entity_id=subject)],
            business_date=day,
            standing=standing,
        ),
    )


def recorder() -> Lake:
    plugin = Lake("ny-fed")

    def resolved(params: ops.ResolveIdentifierParams) -> ops.ResolveIdentifierResult:
        code = params.identifiers[0].value
        if code == NOT_HELD:
            return ops.ResolveIdentifierResult(found=False, miss_reason=ops.MISS_REASON_NOT_FOUND)
        return ops.ResolveIdentifierResult(found=True, instrument_id=instrument_of(code))

    plugin.answer("ResolveIdentifier", resolved)
    return plugin


def _feed() -> Feed:
    return Feed(recorder(), SyntheticApi(lambda: AT), RawStore(), now=lambda: AT)


async def synthetic_feed() -> Feed:
    """A feed as sample data leaves it, on the stand-in lake."""
    feed = _feed()
    await feed.check()
    await feed.backfill()
    sofr = instrument_of("SOFR")
    await feed.on_want(_want("want-0925", sofr, "2026-09-25"))
    await feed.on_want(_want("want-1017", sofr, "2026-10-17"))
    await feed.on_want(_want("want-standing", sofr, standing=True))
    return feed


def render(page: str) -> str:
    feed = _feed() if page.endswith("-first") else asyncio.run(synthetic_feed())
    hold(feed)
    answer = PageClient(pages).get(PAGES[page], "admin")
    if answer.status != 200:
        raise SystemExit(f"{page} answered {answer.status}: {answer.text[:200]}")
    return answer.text


def main() -> None:
    page = sys.argv[1] if len(sys.argv) > 1 else "connection"
    if page not in PAGES:
        raise SystemExit(f"no page {page!r}: {', '.join(PAGES)}")
    sys.stdout.write(render(page))


if __name__ == "__main__":
    main()
