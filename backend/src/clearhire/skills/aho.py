"""Aho–Corasick multi-pattern search with whole-word boundaries.

The reference implementation, in pure Python. `native/` has the same algorithm in C++ (clearhire_native);
`clearhire.skills.matcher` uses whichever is available, and tests/test_native_parity.py checks that both
return identical matches.

A match of pattern p at [start, end) counts only if
  * the character before `start` is not a word character, and
  * unless p is a prefix pattern, the character at `end` is not a word character.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence

from clearhire.text import is_word_char

Match = tuple[int, int, int]  # (pattern index, start, end)


class AhoCorasick:
    def __init__(self, patterns: Sequence[str], prefix: Sequence[bool] | None = None) -> None:
        if prefix is not None and len(prefix) != len(patterns):
            raise ValueError("prefix flags must match the patterns")
        self.patterns = list(patterns)
        self.prefix = list(prefix) if prefix is not None else [False] * len(patterns)
        self._goto: list[dict[str, int]] = [{}]
        self._fail: list[int] = [0]
        self._out: list[list[int]] = [[]]
        for index, pattern in enumerate(self.patterns):
            if not pattern:
                raise ValueError("empty pattern")
            node = 0
            for char in pattern:
                nxt = self._goto[node].get(char)
                if nxt is None:
                    nxt = len(self._goto)
                    self._goto[node][char] = nxt
                    self._goto.append({})
                    self._fail.append(0)
                    self._out.append([])
                node = nxt
            self._out[node].append(index)
        self._link()

    def _link(self) -> None:
        queue: deque[int] = deque(self._goto[0].values())
        while queue:
            node = queue.popleft()
            for char, child in self._goto[node].items():
                queue.append(child)
                fail = self._fail[node]
                while fail and char not in self._goto[fail]:
                    fail = self._fail[fail]
                target = self._goto[fail].get(char, 0)
                self._fail[child] = target if target != child else 0
                self._out[child] = self._out[child] + self._out[self._fail[child]]
        self._out = [sorted(indices) for indices in self._out]

    def find(self, text: str) -> list[Match]:
        """All whole-word matches, ordered by end offset, then by pattern index."""
        matches: list[Match] = []
        node = 0
        goto, fail, out = self._goto, self._fail, self._out
        size = len(text)
        for position, char in enumerate(text):
            while node and char not in goto[node]:
                node = fail[node]
            node = goto[node].get(char, 0)
            if not out[node]:
                continue
            end = position + 1
            for index in out[node]:
                start = end - len(self.patterns[index])
                if start > 0 and is_word_char(text[start - 1]):
                    continue
                if not self.prefix[index] and end < size and is_word_char(text[end]):
                    continue
                matches.append((index, start, end))
        return matches
