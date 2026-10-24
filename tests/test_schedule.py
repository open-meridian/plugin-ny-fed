"""When the current rates are read: every five minutes in the publication
windows, hourly otherwise, never past a window's start."""

from __future__ import annotations

from datetime import UTC, datetime

from ny_fed.schedule import HOURLY, OFTEN, in_window, next_read_in


def utc(hour: int, minute: int, day: int = 23) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


def test_the_windows() -> None:
    assert in_window(utc(12, 0))  # 08:00 ET, Friday
    assert in_window(utc(18, 30))  # 14:30 ET
    assert not in_window(utc(16, 0))  # 12:00 ET
    assert not in_window(utc(12, 0, day=24))  # Saturday
    assert next_read_in(utc(12, 0)) == OFTEN
    assert next_read_in(utc(16, 0)) == HOURLY
    # 07:30 ET: the next read at the window's start, 07:55.
    assert next_read_in(utc(11, 30)) == 25 * 60
    # Friday evening: hourly over the weekend.
    assert next_read_in(utc(23, 0)) == HOURLY
