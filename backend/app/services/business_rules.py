"""Recurring business rules; independent of database rows and calendar years."""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

OPENING_TIME = time(10)
CLOSING_TIME = time(21)
LUNCH_START = time(14)
LUNCH_END = time(15)
WORKING_DAYS = tuple(range(7))  # Monday=0 through Sunday=6


def business_window(day: date, timezone: ZoneInfo, opening: time = OPENING_TIME,
                    closing: time = CLOSING_TIME) -> tuple[datetime, datetime] | None:
    """Intersect a barber's configured hours with the official business hours."""
    start, end = max(opening, OPENING_TIME), min(closing, CLOSING_TIME)
    if day.weekday() not in WORKING_DAYS or start >= end:
        return None
    return datetime.combine(day, start, timezone), datetime.combine(day, end, timezone)


def lunch_window(day: date, timezone: ZoneInfo) -> tuple[datetime, datetime]:
    return datetime.combine(day, LUNCH_START, timezone), datetime.combine(day, LUNCH_END, timezone)


def require_aware(*instants: datetime) -> None:
    if any(instant.utcoffset() is None for instant in instants):
        raise ValueError("Business rules require timezone-aware datetimes")


def within_hours(start: datetime, end: datetime, window: tuple[datetime, datetime]) -> bool:
    require_aware(start, end, *window)
    return window[0] <= start < end <= window[1]


def overlaps_lunch(start: datetime, end: datetime, timezone: ZoneInfo) -> bool:
    require_aware(start, end)
    lunch_start, lunch_end = lunch_window(start.astimezone(timezone).date(), timezone)
    return start < lunch_end and end > lunch_start


def interval_allowed(start: datetime, end: datetime, window: tuple[datetime, datetime],
                     timezone: ZoneInfo) -> bool:
    return within_hours(start, end, window) and not overlaps_lunch(start, end, timezone)


def public_schedule() -> dict:
    return {
        "opening_time": OPENING_TIME.strftime("%H:%M"),
        "closing_time": CLOSING_TIME.strftime("%H:%M"),
        "lunch_start": LUNCH_START.strftime("%H:%M"),
        "lunch_end": LUNCH_END.strftime("%H:%M"),
        "working_days": list(WORKING_DAYS),
    }
