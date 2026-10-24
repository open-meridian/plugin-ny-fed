"""Shared stand-ins: the NY Fed's recorded answer, a fixed clock, the
platform's referential records as the deployment's store answers them, and
the lake's wants as the sidecar delivers them."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.receive import Heard
from meridian.roles.data.testing import Lake

from ny_fed.api import Fetched, SyntheticApi
from ny_fed.feed import Feed
from ny_fed.preview import instrument_of
from ny_fed.raw import RawStore

#: After the recording: 16:45 UTC (12:45 ET) on Friday 23 October 2026.
AT = datetime(2026, 10, 23, 16, 45, tzinfo=UTC)
#: 08:05 ET on 23 October, when the day's rates have appeared.
ET_0805 = datetime(2026, 10, 23, 12, 5, tzinfo=UTC)
INSTANCE = "ny-fed"
DATASET = f"{INSTANCE}:nyfed_rates"
RATE = "meridian.v1.Rate"
RESPONSES = Path(__file__).parent / "responses"
CODES = [
    "SOFR", "EFFR", "OBFR", "TGCR", "BGCR",
    "SOFR 30-day average", "SOFR 90-day average", "SOFR 180-day average", "SOFR Index",
]  # fmt: skip
SOFR = instrument_of("SOFR")


def resolver(ambiguous: str = "", missing: str = "") -> Any:
    """The deployment's store as it answers a referential symbol at `nyfed`:
    `INS-<code>` for each of the nine (`ambiguous` with two records,
    `missing` with none)."""

    def resolved(params: ops.ResolveIdentifierParams) -> ops.ResolveIdentifierResult:
        asked = params.identifiers[0]
        assert (asked.scheme, asked.source) == ("symbol", "nyfed")
        assert params.stated_asset_class == ops.ASSET_CLASS_REFERENTIAL
        if asked.value == ambiguous:
            return ops.ResolveIdentifierResult(found=False, miss_reason=ops.MISS_REASON_AMBIGUOUS)
        if asked.value == missing:
            return ops.ResolveIdentifierResult(found=False, miss_reason=ops.MISS_REASON_NOT_FOUND)
        return ops.ResolveIdentifierResult(found=True, instrument_id=instrument_of(asked.value))

    return resolved


def lake(ambiguous: str = "", missing: str = "") -> Lake:
    """The SDK's lake as a test stands it in (a row key's next version a
    restatement), its store answering as `resolver` does."""
    plugin = Lake(INSTANCE)
    plugin.answer("ResolveIdentifier", resolver(ambiguous, missing))
    return plugin


class Clock:
    """A clock the test moves."""

    def __init__(self, at: datetime = AT) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at

    def move(self, **by: float) -> None:
        self.at += timedelta(**by)


class Revised(SyntheticApi):
    """The NY Fed's API, the current rates read as recorded, then -- from
    the `after`th read on -- with SOFR of 22 October revised from 3.90 to
    3.92 and marked `r`, as the NY Fed revises a rate by 14:30 ET."""

    def __init__(self, now: Any, after: int = 1) -> None:
        super().__init__(now)
        self.reads = 0
        self.after = after

    async def get(self, path: str) -> Fetched:
        self.reads += 1
        return await super().get(path)

    def answer(self, start: Any, end: Any) -> list[dict[str, Any]]:
        held = super().answer(start, end)
        if self.reads <= self.after:
            return held
        out = []
        for one in held:
            if one["type"] == "SOFR" and one["effectiveDate"] == "2026-10-22":
                assert one["percentRate"] == Decimal("3.90")
                one = {**one, "percentRate": Decimal("3.92"), "revisionIndicator": "r"}
            out.append(one)
        return out


class Appearing(SyntheticApi):
    """The API before 08:00 ET on 23 October: SOFR, TGCR, BGCR, EFFR and
    OBFR of 22 October and SOFRAI of 23 October not yet published."""

    def __init__(self, now: Any) -> None:
        super().__init__(now)
        self.clock = now

    def answer(self, start: date, end: date) -> list[dict[str, Any]]:
        held = super().answer(start, end)
        if self.clock() >= ET_0805:
            return held
        return [
            o for o in held
            if o["effectiveDate"] < ("2026-10-23" if o["type"] == "SOFRAI" else "2026-10-22")
        ]  # fmt: skip


def feed(tmp: Path, plugin: Any = None, now: Any = None, api: Any = None) -> Feed:
    """The plugin's work on the stand-in lake and the recorded answer."""
    clock = now or Clock()
    return Feed(
        plugin if plugin is not None else lake(),
        api or SyntheticApi(clock),
        RawStore(tmp),
        now=clock,
    )


def want(
    want_id: str,
    subjects: list[str],
    *,
    day: str = "",
    standing: bool = False,
    data_type: str = RATE,
    dataset: str = DATASET,
    valid_from_ns: int = 0,
    valid_until_ns: int = 0,
) -> Heard:  # type: ignore[type-arg]
    return Heard(
        row="ObservationsWanted",
        message=ops.ObservationsWantedEvent(
            want_id=want_id,
            dataset=dataset,
            data_type=data_type,
            subjects=[ops.SubjectRef(entity_id=s) for s in subjects],
            business_date=day,
            standing=standing,
            valid_from_ns=valid_from_ns,
            valid_until_ns=valid_until_ns,
        ),
    )
