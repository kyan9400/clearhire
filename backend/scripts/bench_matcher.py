"""Skill matching speed: the pure-Python automaton against the C++ extension.

    python scripts/bench_matcher.py [--repeat 5]

Runs both over the text of the synthetic dataset's ground truth (both languages) and prints CVs per second.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from clearhire.skills import Taxonomy, default_taxonomy_text, native_available

DATASET = Path(__file__).resolve().parents[2] / "datasets" / "synthetic" / "candidates.jsonl"


def bench(taxonomy: Taxonomy, texts: list[str], repeat: int) -> float:
    best = float("inf")
    for _ in range(repeat):
        started = time.perf_counter()
        for text in texts:
            taxonomy.find(text)
        best = min(best, time.perf_counter() - started)
    return len(texts) / best


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=5)
    args = parser.parse_args()
    texts = DATASET.read_text(encoding="utf-8").splitlines()
    characters = sum(map(len, texts))
    print(f"{len(texts)} texts, {characters / len(texts):,.0f} characters on average")
    python = bench(Taxonomy.from_yaml(default_taxonomy_text(), native=False), texts, args.repeat)
    print(f"python  {python:10,.0f} texts/s")
    if not native_available():
        print("native  not installed (pip install ./native)")
        return
    native = bench(Taxonomy.from_yaml(default_taxonomy_text(), native=True), texts, args.repeat)
    print(f"native  {native:10,.0f} texts/s  ({native / python:.1f}x)")


if __name__ == "__main__":
    main()
