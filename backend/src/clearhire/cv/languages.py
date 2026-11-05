"""Human languages and their levels, in CVs and in vacancies (CEFR A1–C2, "native", hh.ru phrases)."""

from __future__ import annotations

import re
from dataclasses import dataclass

LEVELS = {1: "A1", 2: "A2", 3: "B1", 4: "B2", 5: "C1", 6: "C2", 7: "Native"}
NATIVE = 7

LANGUAGES: dict[str, tuple[str, ...]] = {
    "en": ("english", "английский", "английского", "английском", "англ"),
    "ru": ("russian", "русский", "русского", "русском"),
    "ar": ("arabic", "арабский", "арабского"),
    "de": ("german", "немецкий", "немецкого"),
    "fr": ("french", "французский", "французского"),
    "es": ("spanish", "испанский", "испанского"),
    "it": ("italian", "итальянский", "итальянского"),
    "zh": ("chinese", "mandarin", "китайский", "китайского"),
    "ja": ("japanese", "японский", "японского"),
    "ko": ("korean", "корейский", "корейского"),
    "tr": ("turkish", "турецкий", "турецкого"),
    "pt": ("portuguese", "португальский"),
    "uk": ("ukrainian", "украинский"),
    "kk": ("kazakh", "казахский"),
    "uz": ("uzbek", "узбекский"),
}
NAMES = {"en": "English", "ru": "Russian", "ar": "Arabic", "de": "German", "fr": "French", "es": "Spanish",
         "it": "Italian", "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "tr": "Turkish",
         "pt": "Portuguese", "uk": "Ukrainian", "kk": "Kazakh", "uz": "Uzbek"}  # fmt: skip

_WORD_TO_LEVEL: list[tuple[str, int]] = [
    # hh.ru's own labels and common phrases first (longest first is enforced below)
    ("в совершенстве", 6), ("свободно владею", 5), ("свободное владение", 5), ("свободный", 5), ("свободно", 5),
    ("могу проходить интервью", 4), ("средне-продвинутый", 4), ("продвинутый", 5),
    ("читаю профессиональную литературу", 2), ("технический", 2), ("элементарный", 2), ("базовый", 2),
    ("начальный", 1), ("средний", 3), ("разговорный", 3), ("родной", 7), ("носитель", 7),
    ("native speaker", 7), ("native", 7), ("mother tongue", 7), ("bilingual", 7),
    ("full professional proficiency", 6), ("proficient", 6), ("professional working proficiency", 5),
    ("fluent", 5), ("advanced", 5), ("upper-intermediate", 4), ("upper intermediate", 4),
    ("pre-intermediate", 2), ("pre intermediate", 2), ("intermediate", 3), ("conversational", 3),
    ("limited working proficiency", 3), ("elementary", 2), ("basic", 2), ("beginner", 1), ("technical", 2),
]  # fmt: skip
_WORD_TO_LEVEL.sort(key=lambda item: len(item[0]), reverse=True)
_CEFR = re.compile(r"(?<![A-Za-z0-9])([ABC])\s?([12])(?![0-9A-Za-zА-Яа-я])\s*(\+)?", re.IGNORECASE)
_NAME_PATTERN = re.compile(
    r"(?<![\w])(" + "|".join(sorted({n for names in LANGUAGES.values() for n in names}, key=len, reverse=True))
    + r")[\w]*\.?",
    re.IGNORECASE,
)
_CODE_BY_NAME = {name: code for code, names in LANGUAGES.items() for name in names}


@dataclass(frozen=True, slots=True)
class LanguageMention:
    code: str
    level: int | None  # 1..7 (A1..C2, native); None when the text gives no level
    span: tuple[int, int]  # the language name and level, as offsets in the text


def level_name(level: int | None) -> str:
    return LEVELS.get(level, "level not stated") if level is not None else "level not stated"


def parse_level(text: str) -> int | None:
    """The highest level stated in `text` ("B2", "C1+", "Upper-Intermediate", "Могу проходить интервью")."""
    lowered = text.lower()
    best: int | None = None
    for match in _CEFR.finditer(text):
        value = (ord(match.group(1).upper()) - ord("A")) * 2 + int(match.group(2))
        best = max(best or 0, value)
    for phrase, value in _WORD_TO_LEVEL:
        if phrase in lowered:
            best = max(best or 0, value)
            lowered = lowered.replace(phrase, " ")
    return best


def find_languages(text: str) -> list[LanguageMention]:
    """Languages named in `text`, each with the level written after it on the same line."""
    found: list[LanguageMention] = []
    matches = list(_NAME_PATTERN.finditer(text))
    for index, match in enumerate(matches):
        code = _CODE_BY_NAME[match.group(1).lower()]
        line_end = text.find("\n", match.end())
        line_end = len(text) if line_end == -1 else line_end
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        window_end = min(line_end, next_start)
        level = parse_level(text[match.end() : window_end])
        found.append(LanguageMention(code, level, (match.start(), window_end)))
    return found
