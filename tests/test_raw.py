"""The NY Fed's answers kept as received, where each rate was first read,
the backfill's progress, and months moved past their window."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from ny_fed.api import Fetched, path_for
from ny_fed.raw import RawStore, range_name

from conftest import AT


def fetched(at: datetime) -> Fetched:
    path = path_for(date(2026, 10, 13), date(2026, 10, 23))
    return Fetched(path, 200, b'{"refRates": []}', at, date="Fri, 23 Oct 2026 16:41:59 GMT")


def test_an_answer_kept_and_read_back(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    key = store.keep(fetched(AT))
    assert key == "responses/2026-10/20261023T164500000000Z-20261013-20261023.json.gz"
    kept = store.read(key)
    assert kept is not None and kept["body"] == '{"refRates": []}' and kept["status"] == 200
    assert kept["url"].startswith("https://markets.newyorkfed.org/api/rates/all/search.json?")
    assert store.read("../outside.json.gz") is None
    assert range_name("/elsewhere") == "answer"


def test_a_rate_names_the_answer_it_was_first_read_from(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    one, two = store.keep(fetched(AT)), store.keep(fetched(AT + timedelta(hours=1)))
    row = "nyfed:fixing:-:act_360:simple:2026-10-22@INS-SOFR"
    day = date(2026, 10, 22)
    first = store.first(row, day, "3.90", one, 123)
    assert first.key == one and first.published_ns == 123
    assert store.first(row, day, "3.90", two, 456) == first
    store.save_firsts()
    # A new process, the same storage: the same answer named.
    assert RawStore(tmp_path).first(row, day, "3.90", two, 0) == first
    # A revision is a new value, noted afresh, naming the answer that revised it.
    assert store.first(row, day, "3.92", two, 789).key == two


def test_the_backfills_progress_by_mode(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    assert store.backfill("live") == {"years": [], "done": False}
    store.note_backfill("live", [2026, 2025], False)
    assert RawStore(tmp_path).backfill("live") == {"years": [2025, 2026], "done": False}
    assert store.backfill("synthetic") == {"years": [], "done": False}


class Mover:
    def __init__(self) -> None:
        self.moved: list[tuple[str, str, int]] = []
        self.stored: list[Any] = []

    async def archive_unit(self, kind: str, unit: str, **span: int) -> None:
        self.moved.append(("archived", unit, span["record_count"]))

    async def delete_unit(self, kind: str, unit: str, **span: int) -> None:
        self.moved.append(("deleted", unit, span["record_count"]))


async def test_months_past_the_window_moved_as_the_setting_says(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    store.keep(fetched(AT - timedelta(days=400)))
    store.keep(fetched(AT - timedelta(days=399)))
    store.keep(fetched(AT))
    mover = Mover()
    done = await store.tend(mover, 365, "archived", AT)  # type: ignore[arg-type]
    assert done["archived"] == 1
    assert mover.moved == [("archived", "responses/2025-09", 2)]
    kept = await store.tend(mover, 365, "kept", AT)  # type: ignore[arg-type]
    assert kept["kept"] == 1
    assert mover.stored[0].record_count == 3


async def test_nothing_moved_without_granted_storage() -> None:
    store = RawStore(None)
    store.granted = False
    store.keep(fetched(datetime(2020, 1, 1, tzinfo=UTC)))
    mover = Mover()
    assert (await store.tend(mover, 1, "deleted", AT))["deleted"] == 0  # type: ignore[arg-type]
    assert mover.moved == []
