"""Chooses the Aho–Corasick implementation: the C++ extension when it is installed, else pure Python.

Set CLEARHIRE_NATIVE=0 to force the Python one (benchmarks and parity tests do).
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Protocol

from clearhire.skills.aho import AhoCorasick, Match


class Matcher(Protocol):
    def find(self, text: str) -> list[Match]: ...


def native_available() -> bool:
    if os.environ.get("CLEARHIRE_NATIVE", "1") == "0":
        return False
    try:
        import clearhire_native  # noqa: F401
    except ImportError:
        return False
    return True


def make_matcher(patterns: Sequence[str], prefix: Sequence[bool], *, native: bool | None = None) -> Matcher:
    use_native = native_available() if native is None else native
    if use_native:
        import clearhire_native

        matcher: Matcher = clearhire_native.Matcher(list(patterns), list(prefix))
        return matcher
    return AhoCorasick(patterns, prefix)
