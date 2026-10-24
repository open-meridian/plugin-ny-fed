"""The two pages under Manage, and their read tools: what each shows, to
whom, and that a tool answers what its page shows."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from meridian.testing import PageClient

from ny_fed import page as page_module
from ny_fed.page import CONNECTION, DATASETS, figures, hold, pages

from conftest import CODES, SOFR, Appearing, Clock, feed, lake, want


@pytest.fixture
def client(tmp_path: Path) -> PageClient:
    clock = Clock(datetime(2026, 10, 23, 12, 0, tzinfo=UTC))
    work = feed(tmp_path, lake(missing="SOFR 180-day average"), clock, Appearing(clock))

    async def run() -> None:
        await work.check()
        clock.at = datetime(2026, 10, 23, 12, 5, tzinfo=UTC)
        await work.check()
        await work.on_want(want("w-0925", [SOFR], day="2026-09-25"))
        await work.on_want(want("w-standing", [SOFR], standing=True))

    asyncio.run(run())
    hold(work)
    return PageClient(pages)


def test_each_page_is_managed_alone(client: PageClient) -> None:
    served = {(r.page.path, r.level): r.response.status for r in client.every_page()}
    assert served == {
        (CONNECTION, "admin"): 200,
        (CONNECTION, "write"): 403,
        (CONNECTION, "read"): 403,
        (DATASETS, "admin"): 200,
        (DATASETS, "write"): 403,
        (DATASETS, "read"): 403,
    }
    # No rate on any page: the NY Fed's figures are the reading roles' to show.
    client.assert_no_account_data("3.90", "1.26398658", "3.75301")


def test_connection_says_how_the_nyfed_is_reached(client: PageClient) -> None:
    text = client.get(CONNECTION, "admin").text
    # The data role's sections, in its order, the NY Fed's Sources a row of
    # Stream, so the page fits one screen.
    assert text.index("<h2>Key</h2>") < text.index("<h2>Limits and use</h2>")
    assert text.index("<h2>Stream</h2>") < text.index(">Sources</th>")
    # No session: a polled plugin's Connection draws no Sessions (SDK 0.32.2).
    assert "<h2>Sessions</h2>" not in text
    assert 'state="warn"' in text and "1 record not held" in text
    assert "No key needed" in text and "Does not stream" in text
    assert text.count("<dd data-source=") == 6 and 'data-sources="6"' in text
    assert "6 sources, latest Fri 23 Oct, next Mon 26 Oct" in text
    assert "Thu 22 Oct" in text  # SOFR's latest effective date
    assert "Mon 26 Oct" in text  # the next SOFR expected: the 23rd's, on Monday
    assert "Monday to Friday" in text
    assert 'href="/.meridian/ui/0.13.0/meridian.css"' in text


def test_datasets_lists_the_dataset_and_every_record(client: PageClient) -> None:
    text = client.get(DATASETS, "admin").text
    assert text.index("<h2>Served</h2>") < text.index("<h2>Wants</h2>")
    assert text.index('<th class="wide-only">Lag</th>') < text.index("<h2>Records</h2>")
    assert "ny-fed:nyfed_rates" in text and "the NY Fed&#39;s notice" in text
    assert "Not licensed yet" in text
    assert text.count("<tr data-code=") == len(CODES)
    assert "<om-pager>" in text and "Kept current" in text
    assert "not found" in text  # the 180-day average, not held
    assert "Terms of Use posted at newyorkfed.org" in text and "DTCC Solutions LLC" in text


def test_the_tools_answer_what_the_pages_show(client: PageClient) -> None:
    names = {t.name for t in pages.tools}
    assert names == {"read_connection", "read_datasets"}
    connection = client.call_tool("read_connection")
    assert connection.outcome == "unchanged", connection.json
    data = connection.data
    assert data["latest_day"] == "2026-10-23" and data["first_day"] == "2026-10-13"
    assert data["mode"] == "Sample data" and data["credentials"] == []
    assert data["sessions"] is None
    sources = {s["source"]: s for s in data["sources"]}
    assert sources["SOFR"]["last_release"] == "2026-10-22"
    assert sources["SOFR"]["next_expected"] == "2026-10-26"
    assert sources["SOFR averages and index"]["next_expected"] == "2026-10-26"
    assert sources["EFFR"]["published_around"] == "09:00 ET"
    datasets = client.call_tool("read_datasets")
    assert datasets.outcome == "unchanged"
    read = datasets.data
    (served,) = read["served"]
    assert served["dataset"] == "ny-fed:nyfed_rates" and served["arrives"] == "push, pull"
    assert served["data"] == "Rate" and served["licensed"] is False
    assert [r["code"] for r in read["records"]] == CODES
    held = {r["code"]: r for r in read["records"]}
    assert held["SOFR"]["instrument_id"] == SOFR and held["SOFR"]["rows"].startswith("Fixing")
    assert held["SOFR 180-day average"]["miss"] == "not found"
    page = client.get(DATASETS, "admin").text
    assert all(r["instrument_id"] in page for r in read["records"] if r["instrument_id"])
    assert read["wants"][0]["want_id"] == "w-standing"
    assert read["wants"][0]["state"] == "Kept current"
    [lag] = read["lag"]
    assert lag["rates"] == 8 and lag["median_seconds"] == 32 * 3600 + 5 * 60
    assert "newyorkfed.org" in read["attribution"]


def test_before_the_first_check() -> None:
    page_module._held.clear()
    text = PageClient(pages).get(CONNECTION, "admin").text
    assert "Checking the NY Fed" in text
    empty = PageClient(pages).get(DATASETS, "admin").text
    assert "No wants yet" in empty and "No rates read yet" in empty


def test_the_nyfed_not_reached(tmp_path: Path) -> None:
    work = feed(tmp_path)
    work.status.error = "https://markets.newyorkfed.org/api: ConnectionRefusedError"
    hold(work)
    text = PageClient(pages).get(CONNECTION, "admin").text
    assert 'state="error"' in text and "Not answering" in text
    assert "ConnectionRefusedError" in text


def test_a_licensed_dataset_is_said_so(client: PageClient) -> None:
    page_module._held["feed"].wants.licensed = frozenset({"ny-fed:nyfed_rates"})
    (served,) = client.call_tool("read_datasets").data["served"]
    assert served["licensed"] is True


def test_the_figures_are_the_data_roles_in_its_order(client: PageClient) -> None:
    work = page_module._held["feed"]
    said = figures(work.status, work)
    assert [f.label for f in said] == [
        "Connection",
        "Entitled at the vendor",
        "Stream",
        "Last recorded",
    ]
    assert said[2].value == "Does not stream"
