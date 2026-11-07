"""Loads the synthetic dataset as a working demo: staff accounts, vacancies, candidates and a pipeline.

Every CV goes through the real pipeline (stored, read, embedded, matched, audited). Applications and
their stage history are spread over the last 60 days, and better matches move further, so the
analytics have something true to show.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from clearhire import audit
from clearhire.db.models import (
    Application,
    Note,
    Role,
    Source,
    Stage,
    StageEvent,
    User,
    Vacancy,
    VacancyStatus,
)
from clearhire.security import hash_password, status_token
from clearhire.services.pipeline import Services, add_candidate, process_document
from clearhire.synth.dataset import load_dataset
from clearhire.synth.generate import neighbours
from clearhire.vacancy import parse_requirements

DEMO_USERS = (
    ("admin@clearhire.demo", "Alex Admin", Role.ADMIN),
    ("recruiter@clearhire.demo", "Rita Recruiter", Role.RECRUITER),
    ("manager@clearhire.demo", "Mark Manager", Role.HIRING_MANAGER),
)
NOTES = {
    "en": ["Clear answers on system design; follow up on testing practices.",
           "Good fit for the team; salary expectations within range.",
           "Strong portfolio; asked about remote work options."],
    "ru": ["Хорошо ответил(а) на вопросы по архитектуре, уточнить опыт тестирования.",
           "Подходит команде, ожидания по зарплате в рамках бюджета.",
           "Сильное портфолио, спрашивал(а) про удаленную работу."],
}  # fmt: skip


async def reset(session: AsyncSession) -> None:
    await session.execute(text(
        "TRUNCATE notes, stage_events, matches, applications, chunks, profiles, documents, candidates, vacancies, "
        "audit_log, users RESTART IDENTITY CASCADE"
    ))  # fmt: skip
    await session.commit()


async def seed(session: AsyncSession, services: Services, root: Path, *, password: str, seed_value: int = 7,
               log: Callable[[str], object] = print) -> dict[str, int]:  # fmt: skip
    rng = random.Random(seed_value)
    now = datetime.now(UTC)
    users = {}
    for email, name, role in DEMO_USERS:
        user = User(email=email, name=name, role=role, password_hash=hash_password(password))
        session.add(user)
        users[role] = user
    await session.flush()
    recruiter = users[Role.RECRUITER]

    truth_candidates, truth_vacancies = load_dataset(root)
    vacancies: dict[str, Vacancy] = {}
    for truth in truth_vacancies:
        requirements = parse_requirements(truth.text, services.matcher.taxonomy)
        description = "\n".join(truth.text.split("\n")[2:]).strip()  # without the title and company lines
        vacancy = Vacancy(title=truth.title, company=truth.company, location="Moscow", remote=True,
                          language=truth.language, description=description,
                          requirements=[r.to_dict() for r in requirements], status=VacancyStatus.OPEN,
                          created_by=recruiter.id)  # fmt: skip
        session.add(vacancy)
        await session.flush()
        vacancy.created_at = now - timedelta(days=rng.randint(45, 75))
        vacancies[truth.id] = vacancy
        await audit.record(session, "vacancy.created", "vacancy", vacancy.id, actor_id=recruiter.id,
                           data={"title": vacancy.title, "requirements": len(requirements)})  # fmt: skip
    await session.commit()

    by_archetype: dict[str, list[str]] = {}
    for truth in truth_vacancies:
        by_archetype.setdefault(truth.archetype, []).append(truth.id)
    applications: list[tuple[Application, str]] = []
    for index, person in enumerate(truth_candidates):
        if index % 25 == 0:
            log(f"candidates {index}/{len(truth_candidates)}")
        data = (root / person.file).read_bytes()
        candidate, document = await add_candidate(
            session, services, data, Path(person.file).name, source=rng.choice([Source.IMPORT, Source.PORTAL, Source.UPLOAD]),
            consent=True, full_name=person.full_name, actor=("system", "seed"),
        )  # fmt: skip
        candidate.city = person.city
        own = by_archetype[person.archetype]
        targets = [own[["junior", "middle", "senior"].index(person.seniority)]]
        for _ in range(rng.choice([0, 0, 1, 2])):
            pool = own + [v for n in neighbours(person.archetype) for v in by_archetype.get(n, [])]
            targets.append(rng.choice(pool))
        for vacancy_key in dict.fromkeys(targets):
            application = Application(candidate_id=candidate.id, vacancy_id=vacancies[vacancy_key].id,
                                      source=candidate.source, status_token=status_token())  # fmt: skip
            session.add(application)
            applications.append((application, person.language))
        await session.commit()
        await process_document(session, services, document.id)

    log("pipeline history")
    from clearhire.db.models import Match

    matches = {(m.candidate_id, m.vacancy_id): m for m in (await session.execute(select(Match))).scalars()}
    for application, language in applications:
        start = now - timedelta(days=rng.randint(2, 60), hours=rng.randint(0, 23))
        application.created_at = start
        session.add(StageEvent(application_id=application.id, stage=Stage.NEW, at=start, by_user=None))
        found = matches.get((application.candidate_id, application.vacancy_id))
        qualified = found is not None and found.must_met == found.must_total
        path: list[Stage] = []
        if rng.random() < (0.85 if qualified else 0.55):
            path.append(Stage.SCREENING)
            if rng.random() < (0.6 if qualified else 0.12):
                path.append(Stage.INTERVIEW)
                if rng.random() < 0.45:
                    path.append(Stage.OFFER)
                    if rng.random() < 0.7:
                        path.append(Stage.HIRED)
            elif rng.random() < 0.7:
                path.append(Stage.REJECTED)
        moment = start
        for stage in path:
            moment = moment + timedelta(days=rng.uniform(1, 6), hours=rng.randint(1, 8))
            if moment > now:
                break
            session.add(
                StageEvent(application_id=application.id, stage=stage, at=moment, by_user=recruiter.id)
            )
            application.stage = stage
            application.updated_at = moment
            if stage == Stage.INTERVIEW:
                session.add(Note(application_id=application.id, author_id=users[Role.HIRING_MANAGER].id,
                                 text=rng.choice(NOTES["ru" if language == "ru" else "en"]), created_at=moment))  # fmt: skip
        if application.stage != Stage.NEW:
            await audit.record(session, "application.stage_changed", "application", application.id,
                               actor_id=recruiter.id, data={"to": application.stage.value, "seeded": True})  # fmt: skip
    await session.commit()
    return {"users": len(users), "vacancies": len(vacancies), "candidates": len(truth_candidates),
            "applications": len(applications)}  # fmt: skip
