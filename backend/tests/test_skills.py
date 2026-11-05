import random

import pytest

from clearhire.skills import Taxonomy, default_taxonomy_text
from clearhire.skills.aho import AhoCorasick
from clearhire.text import fold, is_word_char


def brute_force(patterns: list[str], prefix: list[bool], text: str) -> list[tuple[int, int, int]]:
    found = []
    for end in range(1, len(text) + 1):
        for index, pattern in enumerate(patterns):
            start = end - len(pattern)
            if start < 0 or text[start:end] != pattern:
                continue
            if start > 0 and is_word_char(text[start - 1]):
                continue
            if not prefix[index] and end < len(text) and is_word_char(text[end]):
                continue
            found.append((index, start, end))
    return found


def test_aho_corasick_matches_brute_force_on_random_text() -> None:
    rng = random.Random(7)
    alphabet = "abc +.#-"
    patterns = sorted({"".join(rng.choice("abc+.#") for _ in range(rng.randint(1, 4))) for _ in range(40)})
    prefix = [rng.random() < 0.3 for _ in patterns]
    matcher = AhoCorasick(patterns, prefix)
    for _ in range(200):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 60)))
        assert matcher.find(text) == brute_force(patterns, prefix, text)


def test_fold_keeps_length_and_merges_yo() -> None:
    for text in ["Ёлка İstanbul ẞtraße", "PostgreSQL / ПОСТГРЕС", "C++ & C#"]:
        assert len(fold(text)) == len(text)
    assert fold("ЁЖИК") == "ежик"


def test_taxonomy_has_unique_ids_and_aliases() -> None:
    taxonomy = Taxonomy.from_yaml(default_taxonomy_text(), native=False)  # raises on duplicates
    assert len(taxonomy.skills) > 150
    assert taxonomy.pattern_count > 500


@pytest.mark.parametrize(
    ("text", "expected", "absent"),
    [
        ("Python, Go, SQL", {"python", "go", "sql"}, set()),
        ("We will go to market together", set(), {"go"}),
        ("Golang microservices", {"go", "microservices"}, set()),
        ("Experience with REST APIs and gRPC", {"rest", "grpc"}, set()),
        ("Take a rest; java and javascript", {"java", "javascript"}, {"rest"}),
        ("ASP.NET Core and .NET 8", {"dotnet"}, set()),
        ("C++17, C#, C", {"cpp", "csharp", "c"}, set()),
        ("Деплой в докере и кубернетесе, данные в постгресе", {"docker", "kubernetes", "postgresql"}, set()),
        ("React.js, Next.js, NestJS", {"react", "nextjs", "nestjs"}, set()),
        ("B2B sales, MS Excel", {"excel"}, set()),
        ("Spring Boot, Hibernate", {"spring", "hibernate"}, set()),
        ("In spring 2021 I moved", set(), {"spring"}),
    ],
)
def test_skill_mentions(taxonomy: Taxonomy, text: str, expected: set[str], absent: set[str]) -> None:
    found = taxonomy.skill_ids(text)
    assert expected <= found
    assert not absent & found


def test_mention_offsets_point_into_the_original_text(taxonomy: Taxonomy) -> None:
    text = "Стек: FastAPI, ПостгреСе, Redis"
    for mention in taxonomy.find(text):
        assert text[mention.start : mention.end] == mention.alias


def test_closure_adds_implied_skills(taxonomy: Taxonomy) -> None:
    assert {"python", "fastapi"} <= taxonomy.closure({"fastapi"})
    assert {"react", "javascript"} <= taxonomy.closure({"nextjs"})
    assert {"nodejs", "typescript", "javascript"} <= taxonomy.closure({"nestjs"})
