"""The C++ matcher (native/) must return exactly what the Python reference returns.

Skipped when clearhire_native is not installed; CI builds it and runs these.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from clearhire.skills import Taxonomy, default_taxonomy_text, native_available
from clearhire.skills.aho import AhoCorasick
from conftest import RUSSIAN_CV

pytestmark = pytest.mark.skipif(not native_available(), reason="clearhire_native is not installed")

DATASET = Path(__file__).resolve().parents[2] / "datasets" / "synthetic"

# letters, Cyrillic, Greek, a Latin-1 letter, digits and the separators CVs use: enough to hit every
# boundary rule, and a small alphabet so patterns overlap and share failure links
ALPHABET = "abcаб ж1_-./+#éΩ,\n"


def _native(patterns: list[str], prefix: list[bool]) -> object:
    import clearhire_native

    return clearhire_native.Matcher(patterns, prefix)


def test_random_automata_agree() -> None:
    rng = random.Random(2026)
    for _ in range(300):
        patterns = list(
            dict.fromkeys(
                "".join(rng.choice(ALPHABET.strip()) for _ in range(rng.randint(1, 5)))
                for _ in range(rng.randint(1, 25))
            )
        )
        prefix = [rng.random() < 0.3 for _ in patterns]
        text = "".join(rng.choice(ALPHABET) for _ in range(rng.randint(0, 400)))
        expected = AhoCorasick(patterns, prefix).find(text)
        assert _native(patterns, prefix).find(text) == expected, (patterns, prefix, text)  # type: ignore[attr-defined]


def test_taxonomies_agree_on_cvs() -> None:
    python = Taxonomy.from_yaml(default_taxonomy_text(), native=False)
    native = Taxonomy.from_yaml(default_taxonomy_text(), native=True)
    assert native.native and not python.native
    texts = [RUSSIAN_CV, *_dataset_texts()]
    for text in texts:
        assert [(m.skill_id, m.start, m.end) for m in native.find(text)] == [
            (m.skill_id, m.start, m.end) for m in python.find(text)
        ]


def _dataset_texts() -> list[str]:
    """Ground-truth records hold the bullet text CVs were written from: real-looking input, both languages."""
    path = DATASET / "candidates.jsonl"
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()[:200]
