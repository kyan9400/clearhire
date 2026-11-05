"""Text helpers shared by parsing, skill matching and evidence quotes.

Two rules keep evidence exact:
  * documents are cleaned once, when they are read (`clean_text`), so stored text is what matching sees;
  * matching works on `fold(text)`, which has the same length as `text`, so a match's offsets point
    straight back into the stored text and can be quoted as evidence.
"""

from __future__ import annotations

import re
import unicodedata

_SPACES = re.compile(r"[ \t  -   　]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f­​-‍﻿]")


def clean_text(text: str) -> str:
    """NFKC (ligatures, full-width forms), unified line ends and spaces, no control characters."""
    text = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text)
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def _fold_char(char: str) -> str:
    lower = char.lower()
    if len(lower) != 1:  # "İ".lower() is two code points: keep the original to preserve offsets
        return char
    return "е" if lower == "ё" else lower


class _FoldTable(dict[int, str]):
    """str.translate table that folds each code point the first time it is seen."""

    def __missing__(self, code: int) -> str:
        folded = self[code] = _fold_char(chr(code))
        return folded


_FOLD_TABLE = _FoldTable()


def fold(text: str) -> str:
    """Lower case, "ё" as "е"; always the same length as `text`."""
    return text.translate(_FOLD_TABLE)


def is_word_char(char: str) -> bool:
    """Letters, digits and "_" in the scripts CVs use. Mirrors `is_word_cp` in native/src/matcher.cpp."""
    cp = ord(char)
    if cp < 0x80:
        return char.isalnum() or char == "_"
    return (
        (0x00C0 <= cp <= 0x024F and cp not in (0xD7, 0xF7))
        or 0x0370 <= cp <= 0x03FF
        or 0x0400 <= cp <= 0x052F
        or 0x0531 <= cp <= 0x0587
        or 0x05D0 <= cp <= 0x05EA
        or 0x0620 <= cp <= 0x064A
        or 0x0660 <= cp <= 0x0669
        or 0x06F0 <= cp <= 0x06F9
        or 0x0E00 <= cp <= 0x0E7F
        or 0x1E00 <= cp <= 0x1EFF
        or 0x3040 <= cp <= 0x30FF
        or 0x4E00 <= cp <= 0x9FFF
        or 0xAC00 <= cp <= 0xD7AF
    )


def line_bounds(text: str, position: int) -> tuple[int, int]:
    """Start and end offsets of the line that contains `position`."""
    start = text.rfind("\n", 0, position) + 1
    end = text.find("\n", position)
    return start, len(text) if end == -1 else end


def quote(text: str, start: int, end: int, width: int = 160) -> tuple[str, int, int]:
    """The line around [start, end), cut to about `width` characters at word boundaries.

    Returns the quote and the match's offsets inside it, for highlighting.
    """
    line_start, line_end = line_bounds(text, start)
    line_end = max(line_end, min(end, len(text)))
    if line_end - line_start > width:
        left = max(line_start, start - (width - (end - start)) // 2)
        right = min(line_end, left + width)
        left = max(line_start, right - width)
        if left > line_start:
            space = text.find(" ", left, start)
            left = space + 1 if space != -1 else left
        if right < line_end:
            space = text.rfind(" ", end, right)
            right = space if space != -1 else right
        line_start, line_end = left, right
    snippet = text[line_start:line_end]
    prefix = "… " if line_start > 0 and text[line_start - 1] != "\n" else ""
    suffix = " …" if line_end < len(text) and text[line_end] != "\n" else ""
    return prefix + snippet + suffix, len(prefix) + start - line_start, len(prefix) + end - line_start
