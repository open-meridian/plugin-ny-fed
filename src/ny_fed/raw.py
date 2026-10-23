"""What the NY Fed's API answered, kept as received, in the plugin's own
storage.

A data plugin keeps its source's raw records in the storage the deployment
grants an edge plugin (decisions/028, `meridian.edge.storage_dir()`), and
every row it records names the one it was converted from
(`ObservationMeta.raw`). Here that is each answer of the API's that states
something new: its address, status, the Date header, when it was received,
and the JSON itself, one gzipped JSON file each, kept before anything is
read from it. The API states no Last-Modified, so an answer to the current
range that states exactly what the last one did is not kept again (feed.py
tells them apart by what they state). Raw answers are kept from the first day
(the spec's Q17), so a later version converting more of what the NY Fed
states -- EFFR's old intraday range, a footnote -- needs no refetch.

One kind of raw record, `responses` (declaration.py), in units of a month
of receipt: `responses/<YYYY-MM>/`, each file `<received>-<range>.json.gz`,
its key that path. A month's unit is written to only in that month, so once
its last record is past the kind's window it is moved whole, as the SDK's
`responses_past_window` setting says: archived (`plugin.archive_unit`),
deleted (`plugin.delete_unit`, which a deployment's hold refuses, keeping
it) or kept. The window defaults to ten years.

**Where a rate was first read.** A rate read again -- the next check's
current range, a restart, a reader's want -- names the answer it was first
read from, and the published time noted then, never the newest copy: the
lake compares a row's raw record and source times too, so a new reference
would restate every rate unchanged. Which answer first held each rate, by
its row key and value, is noted under `firsts/<YYYY-MM>.json` at the
storage's root, a file per month of the rates' days. A revised rate is a new
value, so it is noted afresh, naming the answer that revised it.

**History.** The first run's backfill (feed.py) notes each year it has read
under `backfill-<mode>.json`, so a restart goes on where it stopped and a finished
backfill is never read again.

Where no storage is granted -- a test, a preview -- the store keeps its
records in a directory of its own and moves nothing.
"""

from __future__ import annotations

import gzip
import json
import logging
import re
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import meridian
from meridian import edge

from .api import Fetched

log = logging.getLogger("ny_fed")

#: The kind of raw record, and its default window: ten years.
RESPONSES = "responses"
DEFAULT_WINDOW_DAYS = 3650
#: The longest a window may be set to, which the storage declaration states.
MOST_WINDOW_DAYS = 36500
#: Where each rate's first answer is noted, at the storage's root.
FIRSTS = "firsts"
#: Where the backfill's progress is noted, by mode: `backfill-live.json`.
BACKFILL = "backfill-{mode}.json"

_RANGE = re.compile(r"startDate=(\d{4})-(\d{2})-(\d{2})&endDate=(\d{4})-(\d{2})-(\d{2})")


def _ns(moment: datetime) -> int:
    return int(moment.timestamp() * 1_000_000) * 1000


def range_name(path: str) -> str:
    """A short name for the range an address asks: `20261013-20261023`."""
    found = _RANGE.search(path)
    if found is None:
        return "answer"
    return "".join(found.groups()[:3]) + "-" + "".join(found.groups()[3:])


@dataclass(frozen=True)
class First:
    """Where a rate was first read: the answer's key in storage, and its
    published time, 0 where the plugin does not know it."""

    key: str
    published_ns: int = 0


@dataclass(frozen=True)
class Unit:
    """A month of answers: its path in storage, and what it holds."""

    unit: str
    records: int
    first_ns: int
    last_ns: int


class RawStore:
    """Answers kept under `root`: the granted storage, or a directory of the
    store's own where none is granted (`granted` False)."""

    def __init__(self, root: Path | None = None) -> None:
        granted = root if root is not None else edge.storage_dir()
        self.granted = granted is not None
        self.root = (
            Path(granted) if granted is not None else Path(tempfile.mkdtemp(prefix="ny-fed-"))
        )
        self._firsts: dict[str, dict[str, Any]] = {}
        self._dirty: set[str] = set()

    def keep(self, fetched: Fetched) -> str:
        """Keep an answer before anything is read from it; its key."""
        at = fetched.fetched_at.astimezone(UTC)
        unit = f"{RESPONSES}/{at:%Y-%m}"
        key = f"{unit}/{at:%Y%m%dT%H%M%S%fZ}-{range_name(fetched.path)}.json.gz"
        document = {
            "url": fetched.url,
            "status": fetched.status,
            "date": fetched.date,
            "received_at": at.isoformat(),
            "body": fetched.text,
        }
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(".partial")
        partial.write_bytes(gzip.compress(json.dumps(document).encode(), mtime=0))
        partial.replace(target)
        return key

    # ── Where each rate was first read ──────────────────────────────────

    def first(self, row_key: str, day: date, value: str, key: str, published_ns: int) -> First:
        """Where the rate `row_key` stating `value` was first read, noting
        `key` -- the answer it is read from now, at `published_ns` (0 where
        not known) -- if none is noted or storage no longer holds it."""
        month = f"{day:%Y-%m}"
        noted = self._month(month)
        name = f"{row_key}={value}"
        held = noted.get(name)
        if isinstance(held, dict) and (self.root / str(held.get("key", ""))).is_file():
            return First(str(held["key"]), int(held.get("published_ns", 0)))
        made = First(key, published_ns)
        noted[name] = {"key": made.key, "published_ns": made.published_ns}
        self._dirty.add(month)
        return made

    def save_firsts(self) -> None:
        """Write the months noted since the last save."""
        for month in sorted(self._dirty):
            target = self.root / FIRSTS / f"{month}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_suffix(".partial")
            partial.write_text(json.dumps(self._firsts[month], sort_keys=True, indent=0))
            partial.replace(target)
        self._dirty.clear()

    def _month(self, month: str) -> dict[str, Any]:
        held = self._firsts.get(month)
        if held is None:
            try:
                held = json.loads((self.root / FIRSTS / f"{month}.json").read_text())
            except (OSError, ValueError):
                held = {}
            if not isinstance(held, dict):
                held = {}
            self._firsts[month] = held
        return held

    # ── The backfill's progress ─────────────────────────────────────────

    def backfill(self, mode: str) -> dict[str, Any]:
        """The backfill's progress as noted for `mode` (live, or sample
        data's): the years read, and whether it finished."""
        try:
            held = json.loads((self.root / BACKFILL.format(mode=mode)).read_text())
        except (OSError, ValueError):
            return {"years": [], "done": False}
        return held if isinstance(held, dict) else {"years": [], "done": False}

    def note_backfill(self, mode: str, years: list[int], done: bool) -> None:
        target = self.root / BACKFILL.format(mode=mode)
        partial = target.with_suffix(".partial")
        partial.write_text(json.dumps({"years": sorted(set(years)), "done": done}))
        partial.replace(target)

    # ── Reading back and moving ─────────────────────────────────────────

    def read(self, key: str) -> dict[str, Any] | None:
        """A kept answer by its key, or None where storage no longer holds it."""
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()) or not path.is_file():
            return None
        document: dict[str, Any] = json.loads(gzip.decompress(path.read_bytes()))
        return document

    def keys(self) -> list[str]:
        """Every kept answer's key, oldest first."""
        held = self.root / RESPONSES
        if not held.is_dir():
            return []
        return sorted(str(p.relative_to(self.root)) for p in held.glob("*/*.json.gz"))

    def units(self) -> Iterator[Unit]:
        """Each month of answers in storage, oldest first."""
        held = self.root / RESPONSES
        if not held.is_dir():
            return
        for month in sorted(p for p in held.iterdir() if p.is_dir()):
            read = (_received(p.name) for p in month.glob("*.json.gz"))
            stamps = sorted(s for s in read if s is not None)
            if stamps:
                yield Unit(
                    str(month.relative_to(self.root)), len(stamps), _ns(stamps[0]), _ns(stamps[-1])
                )

    async def tend(
        self, plugin: meridian.Plugin, window_days: int, past_window: str, now: datetime
    ) -> dict[str, int]:
        """Move each month past the window as `past_window` says, and say on
        the heartbeat what storage holds; what it came to."""
        done = {"archived": 0, "deleted": 0, "kept": 0, "refused": 0}
        if not self.granted:
            return done
        cut = _ns(now - timedelta(days=window_days))
        this_month = f"{RESPONSES}/{now.astimezone(UTC):%Y-%m}"
        for unit in list(self.units()):
            if unit.last_ns >= cut or unit.unit == this_month:
                continue
            if past_window not in ("archived", "deleted"):
                done["kept"] += 1
                continue
            move = plugin.archive_unit if past_window == "archived" else plugin.delete_unit
            try:
                await move(
                    RESPONSES,
                    unit.unit,
                    record_count=unit.records,
                    first_received_ns=unit.first_ns,
                    last_received_ns=unit.last_ns,
                )
                done[past_window] += 1
            except meridian.MeridianError as refused:
                log.warning("%s: %s refused, kept: %s", unit.unit, past_window, refused)
                done["refused"] += 1
        plugin.stored = [self.span()]
        return done

    def span(self) -> Any:
        """What storage holds of the kind, for the heartbeat."""
        from meridian.v1 import sidecar_pb2

        units = list(self.units())
        return sidecar_pb2.StoredSpan(
            record_kind=RESPONSES,
            record_count=sum(u.records for u in units),
            first_received_ns=units[0].first_ns if units else 0,
            last_received_ns=units[-1].last_ns if units else 0,
        )


def _received(name: str) -> datetime | None:
    try:
        return datetime.strptime(name.split("-", 1)[0], "%Y%m%dT%H%M%S%fZ").replace(tzinfo=UTC)
    except ValueError:
        return None
