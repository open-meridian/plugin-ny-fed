"""When the plugin reads the current rates next: every five minutes in the
NY Fed's publication windows, hourly otherwise.

The NY Fed publishes SOFR, TGCR and BGCR at about 08:00 ET each business
day, the SOFR averages and index shortly after, and EFFR and OBFR at about
09:00 ET; it revises a rate, when it does, at about 14:30 ET the same day
(its reference rates' additional information). So the plugin reads every
five minutes from 07:55 to 10:30 ET and from 14:25 to 15:15 ET, Monday to
Friday, which states a rate's published time to within five minutes
(feed.py), and hourly at other times, so a publication out of schedule is
still read within the hour.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
#: The read in the publication windows, and outside them, in seconds.
OFTEN = 300
HOURLY = 3600
#: The publication windows, New York time, Monday to Friday.
WINDOWS = ((time(7, 55), time(10, 30)), (time(14, 25), time(15, 15)))


def in_window(moment: datetime) -> bool:
    """Whether `moment` is in a publication window."""
    local = moment.astimezone(NEW_YORK)
    if local.weekday() >= 5:
        return False
    return any(start <= local.time() < end for start, end in WINDOWS)


def next_read_in(moment: datetime) -> float:
    """Seconds until the next read: five minutes in a window, else an hour or
    the next window's start, whichever is sooner."""
    if in_window(moment):
        return OFTEN
    local = moment.astimezone(NEW_YORK)
    for days in range(0, 4):
        day = local.date() + timedelta(days=days)
        if day.weekday() >= 5:
            continue
        for start, _ in WINDOWS:
            opens = datetime.combine(day, start, NEW_YORK)
            if opens > local:
                return float(min(HOURLY, max(1, (opens - local).total_seconds())))
    return HOURLY
