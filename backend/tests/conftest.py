from __future__ import annotations

from datetime import date

import pytest

from clearhire.embeddings import HashEmbedder
from clearhire.skills import Taxonomy, load_taxonomy

TODAY = date(2026, 11, 1)

RUSSIAN_CV = """Анна Смирнова
Женщина, 29 лет, родилась 3 мая 1997
Москва · +7 916 123-45-67 · anna.smirnova@example.com · Telegram: @anna_dev
Опыт работы
ООО «Ромашка» — Senior Python Developer
Январь 2021 — настоящее время
Разработала микросервисы на FastAPI, PostgreSQL и Redis; настроила CI/CD в GitLab CI.
Руководила командой из 4 разработчиков, проводила код-ревью.
Acme Corp — Backend Developer
03.2018 – 12.2020
Built REST APIs with Django and Celery; Kafka consumers for payments.
Образование
МГУ, магистр, прикладная математика, 2018
Навыки
Python, SQL, Docker, Kubernetes
Языки
Английский — B2 (Upper-Intermediate)
"""

VACANCY = """Senior Python Developer
Requirements:
- 5+ years of commercial Python development
- FastAPI or Django
- PostgreSQL and Redis
- Experience with Kafka or RabbitMQ
- English B2+
- Experience mentoring developers
Nice to have:
- Kubernetes
- Go
"""


@pytest.fixture(scope="session")
def taxonomy() -> Taxonomy:
    return load_taxonomy()


@pytest.fixture(scope="session")
def embedder() -> HashEmbedder:
    return HashEmbedder()
