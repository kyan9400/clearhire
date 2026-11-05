from datetime import date

import pytest

from clearhire.cv.dates import find_ranges, merged_months, months_between
from clearhire.cv.languages import find_languages, parse_level
from clearhire.cv.profile import detect_language, extract_profile
from clearhire.cv.sections import split_sections
from clearhire.skills import Taxonomy
from conftest import RUSSIAN_CV, TODAY


@pytest.mark.parametrize(
    ("text", "start", "end", "current"),
    [
        ("Jan 2020 – Present", (2020, 1), (2026, 11), True),
        ("Январь 2021 — настоящее время", (2021, 1), (2026, 11), True),
        ("янв. 2021 — наст. время", (2021, 1), (2026, 11), True),
        ("03.2018 – 12.2020", (2018, 3), (2020, 12), False),
        ("2018-03 - 2019-11", (2018, 3), (2019, 11), False),
        ("2019–2021", (2019, 7), (2021, 6), False),
        ("с 2019 по 2021", (2019, 7), (2021, 6), False),
        ("September 2015 to May 2017", (2015, 9), (2017, 5), False),
        ("05/2022 - н.в.", (2022, 5), (2026, 11), True),
    ],
)
def test_date_ranges(text: str, start: tuple[int, int], end: tuple[int, int], current: bool) -> None:
    (found,) = find_ranges(text, today=TODAY)
    assert (found.start, found.end, found.current) == (start, end, current)


def test_dates_ignore_phone_numbers_and_reversed_ranges() -> None:
    assert find_ranges("+7 919 2019 2021 call me", today=TODAY) == []
    assert find_ranges("2021 – 2019", today=TODAY) == []


def test_months_count_overlaps_once() -> None:
    ranges = find_ranges("01.2020 – 12.2020\n06.2020 – 06.2021\n01.2023 – 12.2023", today=TODAY)
    assert merged_months(ranges) == 18 + 12
    assert months_between((2020, 1), (2020, 12)) == 12


def test_sections_split_at_headings() -> None:
    kinds = [s.kind for s in split_sections("Name\nWORK EXPERIENCE\nx\nКлючевые навыки:\ny\nLanguages\nz")]
    assert kinds == ["header", "experience", "skills", "languages"]


@pytest.mark.parametrize(
    ("text", "level"),
    [("B2", 4), ("C1+", 5), ("Upper-Intermediate", 4), ("Могу проходить интервью", 4), ("native", 7),
     ("Родной", 7), ("Читаю профессиональную литературу", 2), ("fluent", 5), ("B2B sales", None)],
)  # fmt: skip
def test_language_levels(text: str, level: int | None) -> None:
    assert parse_level(text) == level


def test_languages_take_the_level_on_their_own_line() -> None:
    found = {m.code: m.level for m in find_languages("Английский — B2, Немецкий — базовый\nArabic: native")}
    assert found == {"en": 4, "de": 2, "ar": 7}


def test_profile_from_a_russian_cv(taxonomy: Taxonomy) -> None:
    profile = extract_profile(RUSSIAN_CV, taxonomy, today=TODAY)
    assert profile.name == "Анна Смирнова"
    assert [p.months for p in profile.positions] == [71, 34]
    assert profile.total_months == 105
    assert profile.skills["fastapi"].months == 71  # only the current role names FastAPI
    assert profile.skills["kafka"].months == 34
    assert profile.skills["python"].months == 105  # named in one role, implied by Django in the other
    assert profile.skills["kubernetes"].months == 0  # listed in the skills section only
    assert profile.languages["en"].level == 4
    assert profile.education is not None and profile.education.degree == 3
    assert profile.contacts["email"] == ["anna.smirnova@example.com"]
    assert profile.contacts["telegram"] == ["anna_dev"]


def test_position_header_is_the_line_above_the_dates(taxonomy: Taxonomy) -> None:
    profile = extract_profile(RUSSIAN_CV, taxonomy, today=TODAY)
    assert profile.positions[0].title == "ООО «Ромашка» — Senior Python Developer"


def test_cv_language_detection() -> None:
    assert detect_language("Опыт работы на Python") == "ru"
    assert detect_language("Work experience with Python") == "en"


def test_hh_style_layout_dates_before_company(taxonomy: Taxonomy) -> None:
    text = "Опыт работы\nМарт 2020 — Май 2023\nЯндекс\nРазработчик интерфейсов\nReact, TypeScript\n"
    profile = extract_profile(text, taxonomy, today=date(2026, 1, 1))
    (position,) = profile.positions
    assert position.title == "Яндекс — Разработчик интерфейсов"
    assert profile.skills["react"].months == 39
