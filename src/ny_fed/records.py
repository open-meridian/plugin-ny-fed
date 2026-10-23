"""The typed records the pages answer, for a person's page and an agent's
tool alike (contract v12; spec/a-deployment-serves-its-mcp): the data role's
common records (`meridian.roles.data`, spec/plugin-pages-follow-their-role),
each extended with the NY Fed's own fields under the names
spec/a-public-rates-and-filings-data-plugin §5 gives its vendor sections:
Connection's **Sources**, and Datasets' **Records** and **Lag**. The
Connection tab is `read_connection`, the Datasets tab `read_datasets`, each
answering what its page shows, as data, under the role's names.

A data plugin's pages show its connection and its datasets, never a rate
(plans/the-lake-prices-the-book, ruled 2026-10-03): rates are the reading
roles'. So neither record holds one; each says how the NY Fed was reached
and what the plugin serves of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from meridian.roles import data


@dataclass(frozen=True)
class SourceRead:
    """One source the plugin reads, as "Sources" lists it -- one of the NY
    Fed's rate types -- its state, the last effective date it published, the
    next expected, Monday to Friday, at about what time, the calls made of
    the API, and its last error."""

    source: str
    dataset: str
    state: str
    last_release: str = ""
    next_expected: str = ""
    published_around: str = ""
    calls: int = 0
    last_error: str = ""


@dataclass(frozen=True)
class ConnectionRead(data.ConnectionRead):
    """Connection's common fields, then the NY Fed's: the head's status and
    what it means, where it reads, the last check, the current range's first
    and latest effective date, how the next release is expected, each source
    as "Sources" lists it, the reads that stated nothing new, the answers
    kept, and the first run's backfill."""

    #: The head's status: `ok`, `busy`, `warn` or `error`, and what it means.
    state: str = ""
    said: str = ""
    source: str = ""
    checked_at: str = ""
    first_day: str = ""
    latest_day: str = ""
    calendar: str = ""
    sources: list[SourceRead] = field(default_factory=list)
    unchanged_reads: int = 0
    responses_kept: int = 0
    kept_for: str = ""
    #: The backfill of the NY Fed's history: done, the years read, its last error.
    backfill: str = ""
    backfill_error: str = ""


@dataclass(frozen=True)
class RecordRead:
    """One of the nine referential records, as "Records" lists it: the NY
    Fed's code for it (the platform's seeded symbol at `nyfed`), its name,
    what its rows are, the latest effective date stated, and the
    deployment's instrument resolved for it, or why there is none."""

    code: str
    name: str
    rows: str
    latest_day: str
    instrument_id: str
    miss: str


@dataclass(frozen=True)
class LagRead:
    """The "Lag" section: published minus valid time for the dataset's rates
    seen published since the plugin started -- the median and the longest,
    in seconds and in words -- and how many."""

    dataset: str
    rates: int = 0
    median_seconds: int = 0
    longest_seconds: int = 0
    #: The median, and the whole, in words.
    median: str = ""
    said: str = ""


@dataclass(frozen=True)
class DatasetsRead(data.DatasetsRead):
    """Datasets' common fields, then the NY Fed's: the notice, disclaimer
    and attribution its terms ask for, each record ("Records"), the lag of
    its rates ("Lag"), the revisions recorded as next versions, and the
    objects it could not read. Its rows are the role's."""

    served: list[data.Served] = field(default_factory=list)
    wants: list[data.WantHeard] = field(default_factory=list)  # type: ignore[assignment]
    attribution: str = ""
    records: list[RecordRead] = field(default_factory=list)
    lag: list[LagRead] = field(default_factory=list)
    revisions: int = 0
    #: The API's objects that named a rate holding none that reads, each
    #: with how often seen.
    unread: list[str] = field(default_factory=list)
