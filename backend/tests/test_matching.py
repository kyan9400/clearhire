from dataclasses import replace

from clearhire.cv.profile import extract_profile
from clearhire.embeddings import HashEmbedder
from clearhire.fairness import pii_spans, redact_for_display, redact_for_model
from clearhire.matching import duration, index_cv, match, prepare_vacancy, rank
from clearhire.skills import Taxonomy
from clearhire.vacancy import parse_requirement, parse_requirements, vacancy_query_text
from conftest import RUSSIAN_CV, TODAY, VACANCY


def test_requirements_are_parsed_into_checks(taxonomy: Taxonomy) -> None:
    requirements = parse_requirements(VACANCY, taxonomy)
    summary = [(r.kind, r.must, r.skills, r.any_of, r.min_years, r.language, r.min_level) for r in requirements]
    assert summary == [
        ("skill", True, ["python"], False, 5.0, None, None),
        ("skill", True, ["fastapi", "django"], True, None, None, None),
        ("skill", True, ["postgresql", "redis"], False, None, None, None),
        ("skill", True, ["kafka", "rabbitmq"], True, None, None, None),
        ("language", True, [], False, None, "en", 4),
        ("skill", True, ["team_lead"], False, None, None, None),
        ("skill", False, ["kubernetes"], False, None, None, None),
        ("skill", False, ["go"], False, None, None, None),
    ]
    assert [r.weight for r in requirements] == [1.0] * 6 + [0.5] * 2


def test_russian_requirement_lines(taxonomy: Taxonomy) -> None:
    years = parse_requirement("Опыт коммерческой разработки на Python от 3 лет", taxonomy, must=True, rid="r1")
    assert (years.kind, years.skills, years.min_years) == ("skill", ["python"], 3.0)
    language = parse_requirement("Английский язык не ниже B1", taxonomy, must=True, rid="r2")
    assert (language.kind, language.language, language.min_level) == ("language", "en", 3)
    total = parse_requirement("Общий опыт работы в разработке не менее 4 лет", taxonomy, must=True, rid="r3")
    assert (total.kind, total.min_years) == ("experience", 4.0)
    degree = parse_requirement("Высшее техническое образование", taxonomy, must=False, rid="r4")
    assert (degree.kind, degree.min_degree) == ("education", 2)


def test_match_reports_each_requirement_with_evidence(taxonomy: Taxonomy, embedder: HashEmbedder) -> None:
    profile = extract_profile(RUSSIAN_CV, taxonomy, today=TODAY)
    cv = index_cv(profile, embedder)
    vacancy = prepare_vacancy(parse_requirements(VACANCY, taxonomy), vacancy_query_text("Python", VACANCY), embedder)
    result = match(cv, vacancy, taxonomy)
    statuses = [r.status for r in result.results]
    assert statuses == ["met", "met", "met", "met", "met", "met", "met", "missing"]
    assert result.must_have_gaps == 0
    assert result.score == round((6 + 0.5) / 7, 4)
    kafka = result.results[3]
    assert "Kafka consumers" in kafka.evidence[0].quote
    assert kafka.evidence[0].section == "experience"
    quote = kafka.evidence[0]
    assert quote.quote[quote.highlight[0] : quote.highlight[1]] == "Kafka"


def test_years_below_the_requirement_are_partial_or_missing(taxonomy: Taxonomy, embedder: HashEmbedder) -> None:
    profile = extract_profile(RUSSIAN_CV, taxonomy, today=TODAY)
    cv = index_cv(profile, embedder)
    lines = "Requirements:\n- Kafka: 4+ years\n- Kubernetes: 2+ years\n- FastAPI: 20+ years"
    vacancy = prepare_vacancy(parse_requirements(lines, taxonomy), lines, embedder)
    kafka, kubernetes, fastapi = match(cv, vacancy, taxonomy).results
    assert kafka.status == "partial"  # 2 years 10 months of 4 years
    assert kubernetes.status == "partial"  # listed, but no dated role shows it
    assert fastapi.status == "missing"
    assert "only 5 years 11 months shown" in fastapi.detail


def test_must_have_gaps_rank_before_score(taxonomy: Taxonomy, embedder: HashEmbedder) -> None:
    strong = extract_profile(RUSSIAN_CV, taxonomy, today=TODAY)
    weak = extract_profile(RUSSIAN_CV.replace("Kafka consumers", "Queue consumers"), taxonomy, today=TODAY)
    vacancy = prepare_vacancy(parse_requirements(VACANCY, taxonomy), VACANCY, embedder)
    ranking = rank([index_cv(weak, embedder), index_cv(strong, embedder)], vacancy, taxonomy)
    assert [index for index, _ in ranking] == [1, 0]
    assert ranking[1][1].must_have_gaps == 1


def test_personal_details_never_reach_the_model(taxonomy: Taxonomy) -> None:
    profile = extract_profile(RUSSIAN_CV, taxonomy, today=TODAY)
    spans = pii_spans(profile)
    labels = {label for _, _, label in spans}
    assert {"name", "gender, age", "birth date", "phone", "email", "telegram"} <= labels
    redacted = redact_for_model(profile.text, (0, len(profile.text)), spans)
    for detail in ("Анна", "Смирнова", "29 лет", "1997", "anna.smirnova", "916"):
        assert detail not in redacted
    shown = redact_for_display(profile.text, spans)
    assert len(shown) == len(profile.text)
    assert "Смирнова" not in shown


def test_swapping_name_gender_and_age_changes_no_score(taxonomy: Taxonomy, embedder: HashEmbedder) -> None:
    variant = (
        RUSSIAN_CV.replace("Анна Смирнова", "Мухаммад Аль-Хасан")
        .replace("Женщина, 29 лет, родилась 3 мая 1997", "Мужчина, 47 лет, родился 9 января 1979")
        .replace("anna.smirnova@example.com", "m.alhasan@example.com")
        .replace("@anna_dev", "@mhasan")
    )
    vacancy = prepare_vacancy(parse_requirements(VACANCY, taxonomy), VACANCY, embedder)
    scores = []
    for text in (RUSSIAN_CV, variant):
        cv = index_cv(extract_profile(text, taxonomy, today=TODAY), embedder)
        result = match(cv, vacancy, taxonomy)
        scores.append((result.score, result.must_have_gaps, result.semantic))
    assert scores[0] == scores[1]


def test_without_blind_mode_the_name_moves_similarity(taxonomy: Taxonomy) -> None:
    embedder = HashEmbedder()
    profile = extract_profile(RUSSIAN_CV, taxonomy, today=TODAY)
    # the header is never embedded; a name inside a passage is what blind mode removes
    text = RUSSIAN_CV.replace("Руководила командой", "Анна Смирнова руководила командой")
    with_name = extract_profile(text, taxonomy, today=TODAY)
    other = extract_profile(text.replace("Анна Смирнова", "Ли Вэй"), taxonomy, today=TODAY)
    blind = [index_cv(p, embedder, blind=True).vectors for p in (with_name, other)]
    open_ = [index_cv(p, embedder, blind=False).vectors for p in (with_name, other)]
    assert (blind[0] == blind[1]).all()
    assert not (open_[0] == open_[1]).all()
    assert replace(profile).name == "Анна Смирнова"


def test_duration_wording() -> None:
    assert duration(1) == "1 month"
    assert duration(12) == "1 year"
    assert duration(29) == "2 years 5 months"
