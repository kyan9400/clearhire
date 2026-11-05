"""Ranking metrics and a BM25 keyword baseline."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

from clearhire.text import fold

_TOKEN = re.compile(r"[^\W_]+")


def dcg(gains: Sequence[float]) -> float:
    return sum((2**gain - 1) / math.log2(index + 2) for index, gain in enumerate(gains))


def ndcg_at(ranked_grades: Sequence[int], all_grades: Sequence[int], k: int) -> float:
    ideal = dcg(sorted(all_grades, reverse=True)[:k])
    return dcg(ranked_grades[:k]) / ideal if ideal else 0.0


def precision_at(ranked_grades: Sequence[int], k: int, threshold: int = 2) -> float:
    top = ranked_grades[:k]
    return sum(1 for g in top if g >= threshold) / k if top else 0.0


def recall_at(ranked_grades: Sequence[int], all_grades: Sequence[int], k: int, threshold: int = 2) -> float:
    relevant = sum(1 for g in all_grades if g >= threshold)
    return sum(1 for g in ranked_grades[:k] if g >= threshold) / relevant if relevant else 0.0


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(fold(text))


class BM25:
    """Okapi BM25 over lower-cased words: the keyword search most CV databases offer."""

    def __init__(self, documents: Sequence[str], k1: float = 1.2, b: float = 0.75) -> None:
        self.docs = [Counter(tokens(d)) for d in documents]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.average = sum(self.lengths) / len(self.lengths) if self.lengths else 0.0
        frequency: Counter[str] = Counter()
        for doc in self.docs:
            frequency.update(doc.keys())
        n = len(self.docs)
        self.idf = {term: math.log1p((n - df + 0.5) / (df + 0.5)) for term, df in frequency.items()}
        self.k1, self.b = k1, b

    def scores(self, query: str) -> list[float]:
        terms = Counter(tokens(query))
        out = []
        for doc, length in zip(self.docs, self.lengths, strict=True):
            score = 0.0
            norm = self.k1 * (1 - self.b + self.b * length / (self.average or 1))
            for term, count in terms.items():
                tf = doc.get(term)
                if tf:
                    score += count * self.idf[term] * tf * (self.k1 + 1) / (tf + norm)
            out.append(score)
        return out
