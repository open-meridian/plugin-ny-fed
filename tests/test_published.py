"""The NY Fed's answer read: every figure a Decimal as stated, the old EFFR's
shape, a revision's mark, and what does not read kept aside."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from ny_fed.convert import stated, volume
from ny_fed.published import NotRates, parse

from conftest import RESPONSES


def recorded(name: str) -> str:
    return (RESPONSES / name).read_text(encoding="utf-8")


def test_a_revision_is_marked() -> None:
    """The one rate the NY Fed has marked revised since 2018: OBFR of 18 July 2019."""
    answer = parse(recorded("rates-20190715-20190719.json"))
    revised = [r for r in answer.rates if r.revised]
    assert [(r.rate_type, r.day) for r in revised] == [("OBFR", date(2019, 7, 18))]
    assert revised[0].values["percentRate"] == Decimal("2.38")
    assert not any(r.rate_type == "SOFRAI" for r in answer.rates), "averages began in 2020"


def test_the_old_effr_has_no_percentiles_or_volume() -> None:
    answer = parse(recorded("rates-20000703-20000707.json"))
    assert answer.days[0] == date(2000, 7, 3)
    first = answer.rates[0]
    assert first.rate_type == "EFFR" and first.values == {"percentRate": Decimal("7.03")}
    assert first.percentiles == {} and first.volume_billions is None
    [one] = stated([first])
    assert one.subject.code == "EFFR"


def test_figures_are_read_as_stated() -> None:
    answer = parse('{"refRates": [{"effectiveDate": "2026-10-22", "type": "SOFR", '
                   '"percentRate": 3.90, "percentPercentile1": 3.83, "volumeInBillions": 2945, '
                   '"revisionIndicator": ""}]}')  # fmt: skip
    [one] = answer.rates
    assert str(one.values["percentRate"]) == "3.90"
    assert one.percentiles == {1: Decimal("3.83")}
    money = volume(one.volume_billions)
    assert money is not None and money.amount == 2_945_000_000_000


def test_sofrai_states_four_records() -> None:
    answer = parse('{"refRates": [{"effectiveDate": "2026-10-23", "type": "SOFRAI", '
                   '"average30day": 3.88887, "average90day": 3.75301, "average180day": 3.70633, '
                   '"index": 1.26398658, "revisionIndicator": ""}]}')  # fmt: skip
    codes = [s.subject.code for s in stated(answer.rates)]
    assert codes == ["SOFR 30-day average", "SOFR 90-day average", "SOFR 180-day average",
                     "SOFR Index"]  # fmt: skip


def test_what_does_not_read_is_kept_aside() -> None:
    answer = parse('{"refRates": [{"effectiveDate": "2026-10-22", "type": "SOFR", '
                   '"percentRate": "n/a"}, {"type": "EFFR"}]}')  # fmt: skip
    assert answer.rates == () and len(answer.unread) == 2
    with pytest.raises(NotRates):
        parse("<html>maintenance</html>")
    with pytest.raises(NotRates):
        parse('{"error": "no"}')


def test_the_recording_reads_whole(tmp_path: Path) -> None:
    from ny_fed.api import SyntheticApi

    api = SyntheticApi()
    assert len(api.rates) == 343
    assert (api.first_day, api.last_day) == (date(2026, 8, 3), date(2026, 10, 23))
