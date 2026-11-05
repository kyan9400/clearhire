"""The HTTP API against a real PostgreSQL with pgvector (set CLEARHIRE_TEST_DATABASE_URL).

docker compose up -d postgres
CLEARHIRE_TEST_DATABASE_URL=postgresql+asyncpg://clearhire:clearhire@localhost:55432/clearhire_test pytest
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import create_async_engine

from clearhire import tasks
from clearhire.config import get_settings
from clearhire.db import session as db_session
from clearhire.db.models import AuditEntry, Base, Role, User
from clearhire.security import hash_password
from conftest import RUSSIAN_CV, VACANCY

pytestmark = pytest.mark.postgres
PASSWORD = "correct horse battery staple"


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("CLEARHIRE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("set CLEARHIRE_TEST_DATABASE_URL to run the API tests")
    return url


def _reset_caches() -> None:
    get_settings.cache_clear()
    db_session.engine.cache_clear()
    db_session.sessions.cache_clear()
    tasks._services = None


async def _fresh_schema(url: str) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.run_sync(Base.metadata.drop_all)
        for name in ("stage", "source", "documentstatus", "vacancystatus", "role"):
            await connection.execute(text(f"DROP TYPE IF EXISTS {name} CASCADE"))
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture
async def api(
    database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    for key, value in {
        "CLEARHIRE_DATABASE_URL": database_url, "CLEARHIRE_EMBEDDING_MODEL": "hash", "CLEARHIRE_DEBUG": "1",
        "CLEARHIRE_STORAGE_DIR": str(tmp_path / "files"),
    }.items():  # fmt: skip
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("CLEARHIRE_REDIS_URL", raising=False)
    _reset_caches()
    await _fresh_schema(database_url)
    async with db_session.sessions()() as session:
        for email, role in (("admin@test.dev", Role.ADMIN), ("recruiter@test.dev", Role.RECRUITER),
                            ("manager@test.dev", Role.HIRING_MANAGER)):  # fmt: skip
            session.add(
                User(
                    email=email,
                    name=email.split("@")[0].title(),
                    role=role,
                    password_hash=hash_password(PASSWORD),
                )
            )
        await session.commit()

    from clearhire.api import app as app_module
    from clearhire.api.routes import public

    public.limiter.hits.clear()
    app = app_module.create_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield client
    await db_session.engine().dispose()
    _reset_caches()


async def login(api: httpx.AsyncClient, who: str) -> dict[str, str]:
    response = await api.post("/api/auth/login", json={"email": f"{who}@test.dev", "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def vacancy(api: httpx.AsyncClient, headers: dict[str, str], status: str = "open") -> dict[str, object]:
    body = {"title": "Senior Python Developer", "company": "Acme", "description": VACANCY, "status": status}
    response = await api.post("/api/vacancies", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def upload(api: httpx.AsyncClient, headers: dict[str, str], vacancy_id: str | None = None, text_: str = RUSSIAN_CV) -> dict[str, object]:  # fmt: skip
    data = {"consent": "true"} | ({"vacancy_id": vacancy_id} if vacancy_id else {})
    response = await api.post(
        "/api/candidates",
        data=data,
        files={"file": ("cv.txt", text_.encode(), "text/plain")},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    return dict(response.json())


async def test_sign_in_and_roles(api: httpx.AsyncClient) -> None:
    assert (await api.get("/api/vacancies")).status_code == 401
    wrong = await api.post("/api/auth/login", json={"email": "recruiter@test.dev", "password": "nope"})
    assert wrong.status_code == 401
    unknown = await api.post("/api/auth/login", json={"email": "ghost@test.dev", "password": PASSWORD})
    assert unknown.status_code == 401
    manager = await login(api, "manager")
    assert (await api.get("/api/vacancies", headers=manager)).status_code == 200
    body = {"title": "X", "description": "Requirements:\n- Python"}
    assert (await api.post("/api/vacancies", json=body, headers=manager)).status_code == 403
    assert (await api.get("/api/audit", headers=manager)).status_code == 403
    response = await api.post("/api/auth/login", json={"email": "manager@test.dev", "password": PASSWORD})
    refreshed = await api.post("/api/auth/refresh", json={"refresh_token": response.json()["refresh_token"]})
    assert refreshed.status_code == 200
    assert (
        await api.post("/api/auth/refresh", json={"refresh_token": response.json()["access_token"]})
    ).status_code == 401


async def test_vacancy_requirements_are_parsed_and_validated(api: httpx.AsyncClient) -> None:
    recruiter = await login(api, "recruiter")
    created = await vacancy(api, recruiter)
    kinds = [r["kind"] for r in created["requirements"]]  # type: ignore[union-attr]
    assert kinds == ["skill", "skill", "skill", "skill", "language", "skill", "skill", "skill"]
    bad = [{"id": "r1", "text": "Fortran", "kind": "skill", "skills": ["fortran77"]}]
    response = await api.put(
        f"/api/vacancies/{created['id']}/requirements", json={"requirements": bad}, headers=recruiter
    )
    assert response.status_code == 422
    good = [{"id": "r1", "text": "Python 3+ years", "kind": "skill", "skills": ["python"], "min_years": 3}]
    response = await api.put(
        f"/api/vacancies/{created['id']}/requirements", json={"requirements": good}, headers=recruiter
    )
    assert response.status_code == 200
    assert response.json()["requirements_version"] == 2


async def test_uploaded_cv_is_read_ranked_and_explained(api: httpx.AsyncClient) -> None:
    recruiter = await login(api, "recruiter")
    created = await vacancy(api, recruiter)
    candidate = await upload(api, recruiter, str(created["id"]))
    profile = (
        await api.get(f"/api/candidates/{candidate['id']}", params={"blind": "false"}, headers=recruiter)
    ).json()
    assert profile["document_status"] == "parsed"
    assert profile["name"] == "Анна Смирнова"
    assert profile["experience_months"] > 100
    assert {"fastapi", "kafka", "postgresql"} <= set(profile["skills"])

    ranking = (await api.get(f"/api/vacancies/{created['id']}/ranking", headers=recruiter)).json()
    (item,) = ranking["items"]
    assert ranking["blind"] is True
    assert item["name"].startswith("Candidate ")
    assert item["must_met"] == item["must_total"] == 6
    assert item["qualified"] is True

    detail = (
        await api.get(f"/api/vacancies/{created['id']}/matches/{candidate['id']}", headers=recruiter)
    ).json()
    statuses = {r["requirement_id"]: r["status"] for r in detail["results"]}
    assert statuses["r8"] == "missing"  # Go
    kafka = next(r for r in detail["results"] if r["requirement_id"] == "r4")
    quote = kafka["evidence"][0]
    assert quote["quote"][quote["highlight"][0] : quote["highlight"][1]] == "Kafka"
    everything = str(detail)
    assert "Смирнова" not in everything and "anna.smirnova" not in everything  # blind mode


async def test_hiring_managers_always_see_blind_profiles(api: httpx.AsyncClient) -> None:
    recruiter = await login(api, "recruiter")
    manager = await login(api, "manager")
    created = await vacancy(api, recruiter)
    candidate = await upload(api, recruiter, str(created["id"]))
    ranking = (
        await api.get(f"/api/vacancies/{created['id']}/ranking", params={"blind": "false"}, headers=manager)
    ).json()
    assert ranking["blind"] is True
    shown = (
        await api.get(f"/api/candidates/{candidate['id']}", params={"blind": "false"}, headers=manager)
    ).json()
    assert shown["email"] is None and shown["name"].startswith("Candidate ")
    assert (await api.get(f"/api/candidates/{candidate['id']}/cv", headers=manager)).status_code == 403


async def test_public_application_flow(api: httpx.AsyncClient) -> None:
    recruiter = await login(api, "recruiter")
    created = await vacancy(api, recruiter)
    draft = await vacancy(api, recruiter, status="draft")
    listed = (await api.get("/api/public/vacancies")).json()
    assert [v["id"] for v in listed] == [created["id"]]
    assert (await api.get(f"/api/public/vacancies/{draft['id']}")).status_code == 404

    def form(consent: str = "true") -> dict[str, str]:
        return {"full_name": "Anna Smirnova", "email": "anna@example.com", "consent": consent}

    files = {"file": ("cv.txt", RUSSIAN_CV.encode(), "text/plain")}
    response = await api.post(f"/api/public/vacancies/{created['id']}/apply", data=form(), files=files)
    assert response.status_code == 201, response.text
    status = (await api.get(f"/api/public/status/{response.json()['status_token']}")).json()
    assert status == {"vacancy": "Senior Python Developer", "company": "Acme", "stage": "received",
                      "updated_at": status["updated_at"], "cv_read": True}  # fmt: skip
    assert (await api.get("/api/public/status/not-a-token")).status_code == 404
    refused = await api.post(f"/api/public/vacancies/{created['id']}/apply", data=form("false"), files=files)
    assert refused.status_code == 422
    binary = {"file": ("cv.pdf", b"MZ\x90\x00\x03\x00binary", "application/pdf")}
    assert (
        await api.post(f"/api/public/vacancies/{created['id']}/apply", data=form(), files=binary)
    ).status_code == 422


async def test_applications_are_rate_limited(api: httpx.AsyncClient) -> None:
    recruiter = await login(api, "recruiter")
    created = await vacancy(api, recruiter)
    codes = []
    for index in range(12):
        response = await api.post(
            f"/api/public/vacancies/{created['id']}/apply",
            data={"full_name": "Rate Limited", "email": f"r{index}@example.com", "consent": "true"},
            files={"file": ("cv.txt", b"Python developer\nPython, SQL", "text/plain")},
        )
        codes.append(response.status_code)
    assert codes[:10] == [201] * 10
    assert codes[10:] == [429, 429]


async def test_stage_changes_feed_analytics_and_the_audit_log(api: httpx.AsyncClient) -> None:
    recruiter = await login(api, "recruiter")
    created = await vacancy(api, recruiter)
    candidate = await upload(api, recruiter, str(created["id"]))
    (application,) = candidate["applications"]  # type: ignore[misc]
    for stage in ("screening", "interview", "offer", "hired"):
        response = await api.patch(
            f"/api/applications/{application['id']}", json={"stage": stage}, headers=recruiter
        )
        assert response.status_code == 200
    overview = (await api.get("/api/analytics/overview", headers=recruiter)).json()
    assert overview["by_stage"]["hired"] == 1
    assert overview["time_to_hire"]["hires"] == 1
    assert [f["reached"] for f in overview["funnel"]] == [1, 1, 1, 1, 1]
    entries = (await api.get("/api/audit", params={"entity_id": application["id"]}, headers=recruiter)).json()
    assert [e["data"]["to"] for e in entries] == ["hired", "offer", "interview", "screening"]
    verified = (await api.get("/api/audit/verify", headers=recruiter)).json()
    assert verified["valid"] is True and verified["entries"] > 5


async def test_tampering_with_the_audit_log_is_detected(api: httpx.AsyncClient) -> None:
    recruiter = await login(api, "recruiter")
    created = await vacancy(api, recruiter)
    await upload(api, recruiter, str(created["id"]))
    entries = (await api.get("/api/audit", headers=recruiter)).json()
    target = min(e["id"] for e in entries if e["action"] == "vacancy.created")
    async with db_session.sessions()() as session:
        await session.execute(
            update(AuditEntry).where(AuditEntry.id == target).values(data={"title": "rewritten"})
        )
        await session.commit()
    verified = (await api.get("/api/audit/verify", headers=recruiter)).json()
    assert verified["valid"] is False
    assert verified["first_bad_id"] == target


async def test_erasure_removes_the_candidate_and_their_file(api: httpx.AsyncClient, tmp_path: Path) -> None:
    recruiter = await login(api, "recruiter")
    created = await vacancy(api, recruiter)
    candidate = await upload(api, recruiter, str(created["id"]))
    files = list((tmp_path / "files").rglob("*"))
    assert any(f.is_file() for f in files)
    assert (await api.delete(f"/api/candidates/{candidate['id']}", headers=recruiter)).status_code == 204
    assert (await api.get(f"/api/candidates/{candidate['id']}", headers=recruiter)).status_code == 404
    assert not any(f.is_file() for f in (tmp_path / "files").rglob("*"))
    ranking = (await api.get(f"/api/vacancies/{created['id']}/ranking", headers=recruiter)).json()
    assert ranking["total"] == 0
    erased = (await api.get("/api/audit", params={"action": "candidate.erased"}, headers=recruiter)).json()
    assert erased[0]["entity_id"] == candidate["id"] and "Смирнова" not in str(erased)


async def test_search_finds_candidates_by_skill_text_and_filters(api: httpx.AsyncClient) -> None:
    recruiter = await login(api, "recruiter")
    await upload(api, recruiter)
    other = "Ivan Petrov\nWork Experience\nDesigner — Studio\nJan 2023 – Present\n• Designed flows in Figma.\nSkills\nFigma"
    await upload(api, recruiter, text_=other)
    hits = (
        await api.get("/api/candidates/search", params={"q": "Kafka", "blind": "false"}, headers=recruiter)
    ).json()
    assert hits[0]["name"] == "Анна Смирнова"
    filtered = (
        await api.get("/api/candidates/search", params={"skills": ["figma"]}, headers=recruiter)
    ).json()
    assert len(filtered) == 1
    experienced = (await api.get("/api/candidates/search", params={"min_years": 5}, headers=recruiter)).json()
    assert len(experienced) == 1


async def test_read_only_demo_blocks_changes(api: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    recruiter = await login(api, "recruiter")
    created = await vacancy(api, recruiter)
    tasks.build_services().settings.demo_read_only = True
    try:
        response = await api.patch(
            f"/api/vacancies/{created['id']}", json={"title": "Changed"}, headers=recruiter
        )
        assert response.status_code == 403
        assert (await api.get(f"/api/vacancies/{created['id']}", headers=recruiter)).status_code == 200
    finally:
        tasks.build_services().settings.demo_read_only = False


async def test_health_and_metrics(api: httpx.AsyncClient) -> None:
    health = (await api.get("/api/health")).json()
    assert health["status"] == "ok" and health["database"] is True
    await api.get("/api/vacancies")
    metrics = (await api.get("/metrics")).text
    assert 'clearhire_http_requests_total{method="GET",route="/api/vacancies",status="401"}' in metrics
