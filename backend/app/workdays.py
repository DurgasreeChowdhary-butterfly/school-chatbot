"""Working days for reminder and escalation deadlines, read from config/working_days.json:
which days of the week are working days, which Saturdays, and the school holidays.
School facts live in files, never in code."""
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = Path(os.getenv("WORKING_DAYS_FILE", str(ROOT / "config" / "working_days.json")))
WEEKS = {"Monday to Friday": 5, "Monday to Saturday": 6}


@dataclass(frozen=True)
class WorkingDays:
    days_per_week: int                       # 5 or 6
    working_saturdays: tuple[int, ...] | None  # e.g. (1, 3) = first and third Saturday; None = every Saturday
    holidays: frozenset[date]


def parse(data: dict) -> WorkingDays:
    """Check the file's contents. Raises ValueError with a message a person can act on."""
    week = data.get("week")
    if week not in WEEKS:
        raise ValueError(f"'week' must be one of {list(WEEKS)}, not {week!r}")
    saturdays = data.get("working_saturdays", "all")
    if saturdays == "all":
        saturdays = None
    elif not (isinstance(saturdays, list) and all(isinstance(n, int) and 1 <= n <= 5 for n in saturdays)):
        raise ValueError("'working_saturdays' must be \"all\" or a list of numbers 1 to 5, like [1, 3]")
    days = set()
    for h in data.get("holidays", []):
        try:
            first = date.fromisoformat(h["from"])
            last = date.fromisoformat(h.get("to", h["from"]))
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"Holiday {h!r} needs 'from' (and optional 'to') dates written YYYY-MM-DD") from None
        if last < first:
            raise ValueError(f"Holiday {h.get('name')!r} ends before it starts")
        days.update(first + timedelta(days=n) for n in range((last - first).days + 1))
    return WorkingDays(WEEKS[week], tuple(saturdays) if saturdays is not None else None, frozenset(days))


@lru_cache
def load() -> WorkingDays:
    return parse(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))


def is_working_day(day: date, calendar: WorkingDays | None = None) -> bool:
    calendar = calendar or load()
    if day in calendar.holidays or day.weekday() == 6:  # Sunday
        return False
    if day.weekday() == 5:  # Saturday
        if calendar.days_per_week < 6:
            return False
        week_of_month = (day.day - 1) // 7 + 1
        return calendar.working_saturdays is None or week_of_month in calendar.working_saturdays
    return True


def add_working_days(start: datetime, days: int, calendar: WorkingDays | None = None) -> datetime:
    """The moment `days` working days after `start` (same time of day; non-working days skipped)."""
    calendar = calendar or load()
    moment = start
    while days > 0:
        moment += timedelta(days=1)
        if is_working_day(moment.date(), calendar):
            days -= 1
    return moment


def holidays_in_calendar(text: str) -> list[dict]:
    """Holidays written in a calendar.md "Holidays:" line, e.g. "Diwali 8 to 11 November 2026. Christmas 25 December
    2026. Summer vacation from 1 May 2027." -> [{"name", "from", "to"}] ("to" is None for "from <date>").
    Used to check that config/working_days.json agrees with the knowledge files."""
    line = next((l for l in text.splitlines() if "holidays:" in l.lower()), "")
    found = []
    pattern = re.compile(r"([A-Za-z][A-Za-z' -]*?)\s+(from\s+)?(\d{1,2})(?:\s+to\s+(\d{1,2}))?\s+([A-Za-z]+)\s+(\d{4})")
    for name, open_ended, first, last, month, year in pattern.findall(line.split(":", 1)[-1]):
        start = datetime.strptime(f"{first} {month} {year}", "%d %B %Y").date()
        end = None if open_ended else start.replace(day=int(last)) if last else start
        found.append({"name": name.strip(), "from": start.isoformat(), "to": end.isoformat() if end else None})
    return found
