"""Date ranges in CVs: "Jan 2020 – Present", "янв. 2020 — наст. время", "03.2018 – 05.2020", "2019–2021"."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

YearMonth = tuple[int, int]

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
    "январь": 1, "января": 1, "янв": 1, "февраль": 2, "февраля": 2, "фев": 2, "февр": 2,
    "март": 3, "марта": 3, "мар": 3, "апрель": 4, "апреля": 4, "апр": 4, "май": 5, "мая": 5,
    "июнь": 6, "июня": 6, "июн": 6, "июль": 7, "июля": 7, "июл": 7, "август": 8, "августа": 8,
    "авг": 8, "сентябрь": 9, "сентября": 9, "сен": 9, "сент": 9, "октябрь": 10, "октября": 10,
    "окт": 10, "ноябрь": 11, "ноября": 11, "ноя": 11, "нояб": 11, "декабрь": 12, "декабря": 12,
    "дек": 12,
}  # fmt: skip

_MONTH_NAMES = "|".join(sorted(_MONTHS, key=len, reverse=True))
_YEAR = r"(?<!\d)(?:19[6-9]\d|20[0-4]\d)(?!\d)"
_DATE = (
    rf"(?:(?:\b(?P<{{p}}mname>{_MONTH_NAMES})\.?\s+(?P<{{p}}y1>{_YEAR}))"
    rf"|(?:(?<!\d)(?P<{{p}}mnum>0?[1-9]|1[0-2])\s*[./-]\s*(?P<{{p}}y2>{_YEAR}))"
    rf"|(?:(?P<{{p}}y3>{_YEAR})\s*[./-]\s*(?P<{{p}}mnum2>0[1-9]|1[0-2])(?![0-9]))"
    rf"|(?P<{{p}}y4>{_YEAR}))"
)
_PRESENT = (
    r"(?:present|now|current(?:ly)?|today|to\s+date|till\s+now|ongoing|настоящее\s+время|наст\.?\s*время"
    r"|н\.\s?в\.?|по\s+н\.\s?в\.?|сейчас|текущее\s+время|по\s+настоящее\s+время|по\s+сей\s+день|наст\.?)"
)
_SEPARATOR = r"\s*(?:[-–—―]+|to|till|until|до|по|\.\.\.)\s*"
_RANGE = re.compile(
    rf"(?:(?:from|since|с)\s+)?(?P<start>{_DATE.format(p='s')})"
    rf"(?:{_SEPARATOR}(?:(?P<present>{_PRESENT})|(?P<end>{_DATE.format(p='e')})))",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class DateRange:
    start: YearMonth
    end: YearMonth
    current: bool
    span: tuple[int, int]  # offsets of the range in the text

    @property
    def months(self) -> int:
        return months_between(self.start, self.end)


def months_between(start: YearMonth, end: YearMonth) -> int:
    """Whole months from `start` to `end`, both included; at least 1."""
    return max(1, (end[0] * 12 + end[1]) - (start[0] * 12 + start[1]) + 1)


def _year_month(match: re.Match[str], prefix: str, *, is_end: bool) -> tuple[YearMonth, bool]:
    """(year, month), and whether the month was written. A bare year counts from July to June,
    so "2019–2021" is two years rather than three."""
    group = match.group
    if group(f"{prefix}mname"):
        return (int(group(f"{prefix}y1")), _MONTHS[group(f"{prefix}mname").lower().rstrip(".")]), True
    if group(f"{prefix}mnum"):
        return (int(group(f"{prefix}y2")), int(group(f"{prefix}mnum"))), True
    if group(f"{prefix}mnum2"):
        return (int(group(f"{prefix}y3")), int(group(f"{prefix}mnum2"))), True
    year = int(group(f"{prefix}y4"))
    return (year, 6 if is_end else 7), False


def find_ranges(text: str, today: date | None = None) -> list[DateRange]:
    """Every date range in `text`, in order. Ranges that end before they start are dropped."""
    today = today or date.today()
    ranges: list[DateRange] = []
    for match in _RANGE.finditer(text):
        start, start_has_month = _year_month(match, "s", is_end=False)
        if match.group("present"):
            end, current = (today.year, today.month), True
        else:
            end, end_has_month = _year_month(match, "e", is_end=True)
            current = False
            if not start_has_month and end_has_month:
                start = (start[0], 1)
            if start_has_month and not end_has_month:
                end = (end[0], 12)
        if (end[0], end[1]) < (start[0], start[1]):
            continue
        if (end[0], end[1]) > (today.year, today.month):
            end = (today.year, today.month)
        ranges.append(DateRange(start, end, current, match.span()))
    return ranges


def merged_months(ranges: list[DateRange]) -> int:
    """Total months covered by the ranges, counting overlapping months once."""
    intervals = sorted((r.start[0] * 12 + r.start[1], r.end[0] * 12 + r.end[1]) for r in ranges)
    total = 0
    current_start, current_end = None, None
    for start, end in intervals:
        if current_end is None or start > current_end + 1:
            if current_end is not None and current_start is not None:
                total += current_end - current_start + 1
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    if current_end is not None and current_start is not None:
        total += current_end - current_start + 1
    return total
