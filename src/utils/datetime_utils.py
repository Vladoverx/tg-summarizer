from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    """Return current UTC time as an aware datetime."""
    return datetime.now(timezone.utc)


def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert a datetime to UTC (aware). Returns None if input is None.

    - If naive, assumes it's already UTC and sets tzinfo=UTC
    - If aware, converts to UTC
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def start_of_utc_day(dt: Optional[datetime] = None) -> datetime:
    """Return the start of day (00:00:00) in UTC for the given datetime or now."""
    base = to_utc(dt) or utc_now()
    return base.replace(hour=0, minute=0, second=0, microsecond=0)


