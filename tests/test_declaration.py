"""The catalogue, from code, as the deployment approves it."""

from __future__ import annotations

from meridian.plugin.v1 import operations_pb2 as ops

from ny_fed.declaration import DECLARATION
from ny_fed.declared import ATTRIBUTION, NYFED_RATES_DATASET


def test_one_daily_dataset_of_rates() -> None:
    assert [d.key for d in DECLARATION.catalogue] == ["nyfed_rates"]
    assert list(NYFED_RATES_DATASET.data_types) == ["meridian.v1.Rate"]
    modes = [ops.ObservationMode.Name(m) for m in NYFED_RATES_DATASET.modes]
    assert modes == ["OBSERVATION_MODE_PUSH", "OBSERVATION_MODE_PULL"]
    assert NYFED_RATES_DATASET.day_time_zone == "America/New_York"
    assert NYFED_RATES_DATASET.day_end_minute == 0
    assert NYFED_RATES_DATASET.cadence == 86_400 and NYFED_RATES_DATASET.history == 9_610
    # No calendar until the US government securities calendar is curated (Q15).
    assert NYFED_RATES_DATASET.calendar_id == ""
    assert not NYFED_RATES_DATASET.venue_id and not NYFED_RATES_DATASET.aggregator


def test_the_nyfeds_terms_are_not_one_persons() -> None:
    licence = NYFED_RATES_DATASET.licence_default
    assert licence is not None
    assert licence.kept and licence.derived_use and licence.display
    assert licence.derived_use_terms == "not_restricted"
    assert not licence.personal_use and licence.retention_days == 0
    assert "Terms of Use posted at newyorkfed.org" in ATTRIBUTION


def test_the_answers_are_kept_in_storage() -> None:
    assert DECLARATION.storage is not None
    assert [k.name for k in DECLARATION.storage.kinds] == ["responses"]
