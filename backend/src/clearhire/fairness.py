"""Blind screening: personal details are hidden from the model, and from reviewers who ask for it.

A name, a photo, contacts, age or birth date, gender, marital status and citizenship say nothing about
whether someone can do the job. They are replaced before the embedding model reads CV text, so they cannot
move a candidate's score; the requirement checks never read them in the first place. The fairness
evaluation (eval/fairness.py) swaps these details between otherwise identical CVs and checks every score.

Russian adds a subtlety the swap test covers too: past-tense verbs carry gender ("разработал" /
"разработала"), so a CV's wording, not only its header, differs between a man and a woman.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clearhire.cv.profile import CandidateProfile

Span = tuple[int, int, str]

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("gender, age", re.compile(r"\b(?:Мужчина|Женщина|Male|Female|Man|Woman)\s*,\s*\d{2}\s*(?:лет|года|год|years old|y\.?o\.?)", re.I)),
    ("age", re.compile(r"\b(?:Возраст|Age)\s*[:\-–—]?\s*\d{2}(?:\s*(?:лет|года|год|years))?", re.I)),
    ("age", re.compile(r"\b\d{2}\s*(?:years old|y\.?o\.?)\b", re.I)),
    ("birth date", re.compile(r"\b(?:Дата рождения|Date of birth|DOB|Born|Родил(?:ся|ась))\s*[:\-–—]?\s*[^\n,;|]{1,40}", re.I)),
    ("gender", re.compile(r"\b(?:Пол|Gender|Sex)\s*[:\-–—]\s*[^\n,;|]{1,20}", re.I)),
    ("marital status", re.compile(r"\b(?:Семейное положение|Marital status)\s*[:\-–—]?\s*[^\n,;|]{1,40}", re.I)),
    ("marital status", re.compile(r"\b(?:женат|замужем|не замужем|холост|разведен[ао]?|married|single|divorced)\b", re.I)),
    ("children", re.compile(r"\b(?:есть дети|дети|children|kids)\s*[:\-–—]?\s*[^\n,;|]{0,20}", re.I)),
    ("citizenship", re.compile(r"\b(?:Гражданство|Citizenship|Nationality|Национальность)\s*[:\-–—]?\s*[^\n,;|]{1,40}", re.I)),
]  # fmt: skip


def pii_spans(profile: CandidateProfile) -> list[Span]:
    """Where personal details are in the CV text: (start, end, label), sorted, not overlapping."""
    text = profile.text
    spans: list[Span] = []
    for label, pattern in _PATTERNS:
        spans.extend((m.start(), m.end(), label) for m in pattern.finditer(text))
    names = set()
    if profile.name:
        names.add(profile.name)
        names.update(part for part in profile.name.split() if len(part) >= 3)
    for name in sorted(names, key=len, reverse=True):
        spans.extend((m.start(), m.end(), "name") for m in re.finditer(rf"(?<![\w]){re.escape(name)}\w*", text))
    for label, values in profile.contacts.items():
        for value in values:
            spans.extend((m.start(), m.end(), label) for m in re.finditer(re.escape(value), text))
    spans.sort()
    merged: list[Span] = []
    for start, end, label in spans:
        if merged and start < merged[-1][1]:
            previous = merged[-1]
            merged[-1] = (previous[0], max(previous[1], end), previous[2])
        else:
            merged.append((start, end, label))
    return merged


def redact_for_model(text: str, window: tuple[int, int], spans: list[Span]) -> str:
    """text[window] with personal details replaced by "[label]" tokens, for the embedding model."""
    start, end = window
    out: list[str] = []
    cursor = start
    for span_start, span_end, label in spans:
        if span_end <= start or span_start >= end:
            continue
        out.append(text[cursor : max(cursor, span_start)])
        out.append(f"[{label}]")
        cursor = max(cursor, min(span_end, end))
    out.append(text[cursor:end])
    return "".join(out)


def redact_for_display(text: str, spans: list[Span]) -> str:
    """Personal details blacked out with "█", keeping every offset, for blind review in the console."""
    chars = list(text)
    for start, end, _label in spans:
        for index in range(start, end):
            if not chars[index].isspace():
                chars[index] = "█"
    return "".join(chars)
