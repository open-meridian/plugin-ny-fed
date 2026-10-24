"""The plugin's pages, under Manage alone: the data role's common pages
(spec/plugin-pages-follow-their-role), Connection and Datasets, in its
order, each also a read tool for agents on the deployment's MCP under the
role's names (`read_connection`, `read_datasets`). Each record is the
role's (`meridian.roles.data`), extended with the NY Fed's fields; each
template is the role's, with the NY Fed's nuance at its blocks only.

A data plugin shows its connectivity, its data subscriptions and how its
entitlements resolve, and no market data (the product owner, 2026-10-03).
So, as spec/a-public-rates-and-filings-data-plugin §5 has them:

- **Connection** (`/`): "Key" -- the mode (Live or Sample data), "No key
  needed", what the NY Fed serves; "Limits and use" -- the NY Fed states no
  limit, the requests made, the last check and error; "Stream": it does not
  stream. Then **Sources**, one line per rate type the API states: its
  state, the last effective date published, the next expected, Monday to
  Friday, its calls, its last error; and the history's backfill.
- **Datasets** (`/datasets`): "Served", "Wants" and "Subjects", then
  **Lag**, the median published-minus-valid time, as a column of Served,
  and **Records**, each of the nine referential records and the
  deployment's instrument for it or why there is none, one line a row,
  under the NY Fed's notice and disclaimer.

Neither shows an account's data, since the plugin reaches none, nor a rate:
rates are the reading roles' to show.
"""

from __future__ import annotations

import statistics
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import meridian
from meridian.roles import data

from . import records
from .api import BASE, SEARCH
from .declared import ATTRIBUTION, NYFED_RATES_DATASET, SUBJECTS
from .feed import Feed, Status

TITLE = "Federal Reserve Bank of New York"
#: The kit these pages are built on: v27's, 0.13.0.
KIT = "0.13.0"

pages = meridian.Pages(TITLE, templates=Path(__file__).parent / "templates", kit=KIT)

CONNECTION = "/"
DATASETS = "/datasets"

#: How many wants the Datasets tab lists; read_datasets answers every one held.
SHOWN_WANTS = 3
#: The API's rate types, each a line of Sources, with what it publishes and
#: about when, New York time.
SOURCES = (
    ("SOFR", "SOFR", "08:00 ET"),
    ("TGCR", "TGCR", "08:00 ET"),
    ("BGCR", "BGCR", "08:00 ET"),
    ("SOFRAI", "SOFR averages and index", "08:00 ET, after SOFR"),
    ("EFFR", "EFFR", "09:00 ET"),
    ("OBFR", "OBFR", "09:00 ET"),
)
KINDS = {"fixing": "Fixing, with percentiles and volume", "average": "Average",
         "index_level": "Index level"}  # fmt: skip

_held: dict[str, Feed] = {}


def hold(feed: Feed) -> None:
    """The feed the pages read, once the plugin has registered."""
    _held["feed"] = feed


def _status() -> tuple[Status, Feed | None]:
    feed = _held.get("feed")
    return (feed.status if feed is not None else Status(), feed)


def _iso(moment: datetime | None) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds") if moment else ""


def _day(day: date | None) -> str:
    return day.isoformat() if day else ""


def _state(status: Status) -> tuple[str, str, str]:
    """The head's status: its state, what it means, and its detail."""
    misses = [h for h in status.held.values() if h.miss and not h.instrument_id]
    read = status.read_at is not None
    if status.error and not read:
        return "error", "Not answering", status.error
    if status.error:
        return "warn", "Answering", status.error
    if not read:
        return "busy", "Checking the NY Fed", ""
    if misses:
        codes = ", ".join(h.subject.code for h in misses)
        plural = "record" if len(misses) == 1 else "records"
        return "warn", f"{len(misses)} {plural} not held", codes
    if status.mode == "synthetic":
        return "ok", "Sample data", ""
    return "ok", "Answering", ""


def _backfill(status: Status) -> str:
    years = status.backfill_years
    if status.backfill_done:
        return f"Done: {min(years)} to {max(years)}" if years else "Done"
    if years:
        return f"Reading: {min(years)} to {max(years)} read"
    return "Not started"


def connection_read(status: Status, feed: Feed | None) -> records.ConnectionRead:
    state, said, _ = _state(status)
    kept = feed.raw.keys() if feed is not None else []
    window = ""
    if feed is not None and feed.raw.granted:
        window = "in the storage the deployment grants, as its responses settings say"
    elif feed is not None:
        window = "in a directory of the plugin's own: this deployment grants no storage"
    dataset = feed.dataset if feed is not None else f"ny-fed:{NYFED_RATES_DATASET.key}"
    answered = status.read_at is not None
    return records.ConnectionRead(
        mode="Sample data" if status.mode == "synthetic" else "Live",
        credentials=[],
        entitled_at_vendor=(
            "Every reference rate the NY Fed publishes: no key" if answered else ""
        ),
        limit=(
            "The NY Fed states none; the plugin asks one request at a time, at most one every "
            "two seconds, every five minutes in the publication windows and hourly otherwise"
        ),
        calls=status.fetches,
        last_call_at=_iso(status.checked_at),
        last_error=status.error,
        sessions=None,
        state=state,
        said=said,
        source=(
            "The answer recorded on 2026-10-23, committed with the plugin"
            if status.mode == "synthetic"
            else f"{BASE}{SEARCH}, every reference rate"
        ),
        checked_at=_iso(status.checked_at),
        first_day=_day(status.first_day),
        latest_day=_day(status.latest_day),
        calendar=(
            "Monday to Friday: no US government securities calendar is held yet, so the "
            "NY Fed's holidays are not known ahead"
        ),
        sources=[
            records.SourceRead(
                source=name,
                dataset=dataset,
                state=said if status.latest_by_type.get(rate_type) else "Not read yet",
                last_release=_day(status.latest_by_type.get(rate_type)),
                next_expected=_day(feed.next_release(rate_type) if feed is not None else None),
                published_around=around,
                calls=status.fetches,
                last_error=status.error,
            )
            for rate_type, name, around in SOURCES
        ],
        unchanged_reads=status.unchanged_reads,
        responses_kept=len(kept),
        kept_for=window,
        backfill=_backfill(status),
        backfill_error=status.backfill_error,
    )


def _duration(seconds: int) -> str:
    hours, rest = divmod(max(seconds, 0), 3600)
    return f"{hours} h {rest // 60:02d} m"


def lag_read(status: Status, dataset: str) -> records.LagRead:
    lags = status.lags
    if not lags:
        return records.LagRead(dataset=dataset, said="No rate seen published yet")
    median, longest = int(statistics.median(lags)), max(lags)
    return records.LagRead(
        dataset=dataset,
        rates=len(lags),
        median_seconds=median,
        longest_seconds=longest,
        median=f"{_duration(median)} median",
        said=f"{_duration(median)} median, {_duration(longest)} longest, of {len(lags)} rates",
    )


def datasets_read(status: Status, feed: Feed | None) -> records.DatasetsRead:
    instance = feed.plugin.identity.instance_id if feed is not None else "ny-fed"
    dataset = f"{instance}:{NYFED_RATES_DATASET.key}"
    answered = status.read_at is not None
    served = data.served(
        [NYFED_RATES_DATASET],
        instance,
        feed.wants if feed is not None else None,
        "Yes: no key needed" if answered else "Not asked yet",
    )
    served = [
        replace(s, default_terms="kept, derived use, display; the NY Fed's notice") for s in served
    ]
    return records.DatasetsRead(
        served=served,
        wants=list(data.want_rows(feed.wants)) if feed is not None else [],
        reads_instruments=True,
        attribution=ATTRIBUTION,
        records=[
            records.RecordRead(
                code=s.code,
                name=s.name,
                rows=KINDS[s.kind],
                latest_day=_day(status.held[s.code].latest_day),
                instrument_id=status.held[s.code].instrument_id,
                miss=status.held[s.code].miss.replace("_", " "),
            )
            for s in SUBJECTS
        ],
        lag=[lag_read(status, dataset)],
        revisions=status.revisions,
        unread=[f"{line} ({n} reads)" for line, n in sorted(status.unread.items())],
    )


def figures(status: Status, feed: Feed | None) -> list[meridian.Figure]:
    """The data role's figures, in its order (`meridian.roles.data`); the
    NY Fed's plugin reports none of its own."""
    state, said, why = _state(status)
    if status.mode == "synthetic" and state == "ok":
        connection: Any = "Sample data"
    elif said == "Not answering":
        connection = meridian.Figure("", said, state="error", why=why[:200])
    else:
        connection = meridian.Figure(
            "", "Answering", state="warn" if status.error else None, why=status.error[:200]
        )
    last = feed.wants.counts.last_ns if feed is not None else 0
    return data.figures(
        connection=connection,
        entitled_at_vendor="1 of 1 datasets",
        stream="Does not stream",
        last_recorded=(datetime.fromtimestamp(last / 10**9, UTC) if last else None),
    )


def _moment(value: str) -> str:
    """An ISO moment as a person reads it, to the minute in UTC."""
    if not value:
        return ""
    if len(value) == 10:
        return value
    return datetime.fromisoformat(value).astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _weekday(value: str) -> str:
    return date.fromisoformat(value).strftime("%a %d %b") if value else ""


pages.environment.filters["moment"] = _moment
pages.environment.filters["day"] = _weekday


@pages.page(
    CONNECTION,
    "Connection",
    levels="admin",
    answers=records.ConnectionRead,
    name="read_connection",
    description=(
        "How this plugin reaches the Federal Reserve Bank of New York's markets data API, as "
        "every data plugin's Connection answers it: the mode (Live or Sample data), no key "
        "needed, what the NY Fed serves, its limits (none stated) and the requests made, the "
        "last check and why it failed if it did; it does not stream. Then the NY Fed's own: "
        "each rate type with its state, the latest effective date published, the next "
        "expected (Monday to Friday) and about when, its calls and last error; the history's "
        "backfill; and how many answers are kept. No rate."
    ),
)
async def connection(request: meridian.Request) -> meridian.Response:
    status, feed = _status()
    read = connection_read(status, feed)
    return pages.answer("connection.html", read, detail=_state(status)[2])


@pages.page(
    DATASETS,
    "Datasets",
    levels="admin",
    answers=records.DatasetsRead,
    name="read_datasets",
    description=(
        "What this plugin serves the lake, as every data plugin's Datasets answers it: its "
        "one dataset as the catalogue declares it (the NY Fed's reference rates as fixings, "
        "averages and an index level, New York's day, kept with the NY Fed's notice), whether "
        "a deployment admin has licensed it, what it recorded and declined; the standing "
        "wants it keeps current and the wants it answered. Then the NY Fed's own: the notice, "
        "disclaimer and attribution its terms ask for, the lag between a rate's day and its "
        "publication, the revisions recorded as next versions, and each of the nine records "
        "with the deployment's instrument for it or why there is none. No rate."
    ),
)
async def datasets(request: meridian.Request) -> meridian.Response:
    status, feed = _status()
    read = datasets_read(status, feed)
    drawn = read if request.tool_name else replace(read, wants=read.wants[:SHOWN_WANTS])
    return pages.answer(
        "datasets.html",
        drawn,
        state=_state(status),
        checked_at=_iso(status.checked_at),
        wants=len(read.wants),
    )
