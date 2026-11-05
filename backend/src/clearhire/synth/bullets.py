"""Achievement sentences for synthetic CVs, in English and Russian, with the skills each one fits.

A template is used only for skills that fit its slots, so a CV never says it "integrated pandas with
partners' systems". Russian "{a}" is "" or "а": past-tense verbs agree with the writer's gender.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations


@dataclass(frozen=True)
class Slot:
    """Which skills fit a place in a sentence: by category, optionally only some ids, or all but some."""

    cats: frozenset[str] = frozenset()  # empty: any category
    only: frozenset[str] = frozenset()
    exclude: frozenset[str] = frozenset()

    def fits(self, skill_id: str, category: str) -> bool:
        if skill_id in self.exclude or (self.only and skill_id not in self.only):
            return False
        return not self.cats or category in self.cats


def _slot(*cats: str, only: tuple[str, ...] = (), exclude: tuple[str, ...] = ()) -> Slot:
    return Slot(frozenset(cats), frozenset(only), frozenset(exclude))


DEV = ("language", "backend", "frontend", "mobile", "database", "blockchain")
OPS = ("devops", "cloud")
NOT_BUILT_WITH = ("sql", "rest", "html", "css", "bash", "linux", "a11y", "nosql")
TOOLS = ("practice", "tool", "testing")
ANY = _slot()

BULLETS: dict[str, tuple[tuple[Slot, ...], str, str]] = {
    "build2": (
        (_slot(*DEV, exclude=NOT_BUILT_WITH), _slot(*DEV, *OPS)),
        "Developed services and features with {s1} and {s2}.",
        "Разработал{a} сервисы и функциональность на {s1} и {s2}.",
    ),
    "maintain2": (
        (_slot(*DEV, exclude=NOT_BUILT_WITH), _slot(*DEV, *OPS)),
        "Maintained and extended the product built on {s1} and {s2}.",
        "Поддерживал{a} и развивал{a} продукт на {s1} и {s2}.",
    ),
    "migrate1": (
        (_slot("backend", "frontend", "mobile", "database", "language", exclude=NOT_BUILT_WITH),),
        "Migrated a legacy module to {s1}, cutting response time by {n}%.",
        "Перевел{a} устаревший модуль на {s1}, сократив время ответа на {n}%.",
    ),
    "intro2": (
        (_slot(*DEV, *OPS, "ml", *TOOLS), _slot(*DEV, *OPS, "ml", *TOOLS)),
        "Introduced {s1} and {s2} into the team's workflow.",
        "Внедрил{a} {s1} и {s2} в процессы команды.",
    ),
    "datamodel2": (
        (_slot("database", exclude=("nosql",)), _slot(*DEV, *OPS, exclude=("sql",))),
        "Designed the data model in {s1} and set up {s2}.",
        "Спроектировал{a} модель данных в {s1} и настроил{a} {s2}.",
    ),
    "automate1": (
        (
            _slot(
                only=(
                    "cicd",
                    "github_actions",
                    "gitlab_ci",
                    "jenkins",
                    "terraform",
                    "ansible",
                    "helm",
                    "docker",
                    "kubernetes",
                    "bash",
                )
            ),
        ),
        "Automated releases with {s1}; deployments went from weekly to daily.",
        "Автоматизировал{a} релизы с помощью {s1}; выкладки стали ежедневными.",
    ),
    "ops2": (
        (
            _slot(*OPS, exclude=("prometheus", "grafana", "elk", "observability", "sentry")),
            _slot(*OPS, "database"),
        ),
        "Kept production running on {s1} and {s2}.",
        "Обеспечивал{a} стабильную работу продакшена на {s1} и {s2}.",
    ),
    "monitor1": (
        (_slot(only=("prometheus", "grafana", "elk", "observability", "sentry")),),
        "Set up monitoring and alerts with {s1}.",
        "Настроил{a} мониторинг и алерты на {s1}.",
    ),
    "tests1": (
        (_slot("testing"),),
        "Covered critical user journeys with tests using {s1}.",
        "Покрыл{a} тестами критичные сценарии с помощью {s1}.",
    ),
    "integrate1": (
        (_slot(only=("kafka", "rabbitmq", "rest", "grpc", "graphql", "websocket")),),
        "Integrated with partners' systems over {s1}.",
        "Интегрировал{a} систему с партнерами через {s1}.",
    ),
    "optimise1": (
        (_slot("backend", "database", "frontend", "language", exclude=NOT_BUILT_WITH),),
        "Optimised slow parts of the system with {s1}.",
        "Оптимизировал{a} медленные участки системы с помощью {s1}.",
    ),
    "screens2": (
        (_slot("design", "frontend"), _slot("design", "frontend")),
        "Designed product flows and screens using {s1} and {s2}.",
        "Спроектировал{a} пользовательские сценарии и экраны с помощью {s1} и {s2}.",
    ),
    "research1": (
        (_slot("design", exclude=("adobe",)),),
        "Ran user research and usability tests with {s1}.",
        "Проводил{a} исследования и юзабилити-тесты с помощью {s1}.",
    ),
    "decide2": (
        (_slot("management", "data", "practice"), _slot("management", "data", "practice", "tool")),
        "Drove product decisions using {s1} and {s2}.",
        "Принимал{a} продуктовые решения на основе {s1} и {s2}.",
    ),
    "process1": (
        (_slot("practice", "tool"),),
        "Improved how the team works with {s1}.",
        "Улучшил{a} процессы команды с помощью {s1}.",
    ),
    "analyse2": (
        (_slot("data"), _slot("data", "language", "database")),
        "Analysed product data with {s1} and {s2}.",
        "Анализировал{a} продуктовые данные с помощью {s1} и {s2}.",
    ),
    "train2": (
        (
            _slot("ml", exclude=("llm", "rag", "agents", "embeddings", "faiss", "ocr")),
            _slot(
                only=(
                    "pandas",
                    "numpy",
                    "scipy",
                    "jupyter",
                    "python",
                    "r",
                    "sklearn",
                    "pytorch",
                    "tensorflow",
                    "gbm",
                    "hf_transformers",
                    "statistics",
                    "nlp",
                    "computer_vision",
                )
            ),
        ),
        "Trained and evaluated models with {s1} and {s2}.",
        "Обучал{a} и оценивал{a} модели с помощью {s1} и {s2}.",
    ),
    "ship1": (
        (_slot("ml", exclude=("llm", "rag", "embeddings", "agents")),),
        "Shipped a model built with {s1} to production.",
        "Вывел{a} в продакшен модель на {s1}.",
    ),
    "assistant2": (
        (
            _slot(only=("llm", "rag", "embeddings", "langchain", "llamaindex", "agents", "hf_transformers")),
            _slot("ml", "backend", "database"),
        ),
        "Built an assistant over company documents with {s1} and {s2}.",
        "Разработал{a} ассистента по документам компании на {s1} и {s2}.",
    ),
    "work3": (
        (ANY, ANY, ANY),
        "Worked with {s1}, {s2} and {s3} on a product with {n}k monthly users.",
        "Работал{a} с {s1}, {s2} и {s3} в продукте с аудиторией {n} тыс. пользователей в месяц.",
    ),
    "use1": ((ANY,), "Used {s1} every day.", "Использовал{a} {s1} в ежедневной работе."),
    "use2": ((ANY, ANY), "Worked with {s1} and {s2}.", "Работал{a} с {s1} и {s2}."),
}
GENERIC = ("use1", "use2", "work3")


def fitting_order(slots: tuple[Slot, ...], skills: list[str], categories: list[str]) -> list[int] | None:
    """An order of the skills that fits the template's slots, if there is one."""
    for order in permutations(range(len(skills))):
        if all(slot.fits(skills[i], categories[i]) for slot, i in zip(slots, order, strict=True)):
            return list(order)
    return None
