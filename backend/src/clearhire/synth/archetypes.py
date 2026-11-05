"""Job roles for the synthetic dataset: their skills, titles and duties, in English and Russian.

Skill lists hold taxonomy ids; a tuple means "one of these". Titles carry the skill ids they name, so the
ground truth never depends on the matcher it is used to test.
"""

from __future__ import annotations

from dataclasses import dataclass

Choice = str | tuple[str, ...]


@dataclass(frozen=True)
class Archetype:
    id: str
    titles_en: tuple[
        tuple[str, tuple[str, ...]], ...
    ]  # (title, skill ids it names) for junior, middle, senior
    titles_ru: tuple[tuple[str, tuple[str, ...]], ...]
    core: tuple[Choice, ...]
    common: tuple[Choice, ...]
    rare: tuple[Choice, ...]
    duties_en: tuple[str, ...]
    duties_ru: tuple[str, ...]
    english: tuple[int, int, int]  # English level asked for junior, middle, senior (CEFR 1..6)


ARCHETYPES: tuple[Archetype, ...] = (
    Archetype(
        "python_backend",
        (("Junior Python Developer", ("python",)), ("Python Developer", ("python",)), ("Senior Python Engineer", ("python",))),
        (("Junior Python-разработчик", ("python",)), ("Python-разработчик", ("python",)), ("Ведущий Python-разработчик", ("python",))),
        ("python", ("django", "fastapi", "flask"), "postgresql", "rest"),
        ("redis", "celery", "docker", "sqlalchemy", ("kafka", "rabbitmq"), "pytest", "git", "linux", "asyncio", "kubernetes", "cicd"),
        ("go", "clickhouse", "elasticsearch", "grpc", "aws"),
        ("Design and build backend services and APIs", "Review code and improve test coverage", "Work with product on new features"),
        ("Разработка и развитие бэкенд-сервисов и API", "Код-ревью и развитие тестов", "Работа с продуктовой командой над новыми функциями"),
        (3, 3, 4),
    ),
    Archetype(
        "java_backend",
        (("Junior Java Developer", ("java",)), ("Java Developer", ("java",)), ("Senior Java Engineer", ("java",))),
        (("Junior Java-разработчик", ("java",)), ("Java-разработчик", ("java",)), ("Ведущий Java-разработчик", ("java",))),
        ("java", "spring", "sql", ("postgresql", "mysql")),
        ("hibernate", "kafka", "docker", "kubernetes", "junit", "microservices", "rest", "git", "rabbitmq"),
        ("kotlin", "redis", "elasticsearch", "aws"),
        ("Develop microservices for the core platform", "Take part in architecture decisions", "Support production releases"),
        ("Разработка микросервисов основной платформы", "Участие в архитектурных решениях", "Поддержка релизов в продакшене"),
        (2, 3, 4),
    ),
    Archetype(
        "frontend_react",
        (("Junior Frontend Developer", ()), ("Frontend Developer (React)", ("react",)), ("Senior Frontend Engineer", ())),
        (("Junior frontend-разработчик", ()), ("Frontend-разработчик (React)", ("react",)), ("Senior frontend-разработчик", ())),
        ("javascript", "typescript", "react", "html", "css"),
        ("redux", "nextjs", "jest", ("webpack", "vite"), ("tailwind", "sass"), "rest", "git", "figma"),
        ("vue", "graphql", "storybook", "cypress", "threejs"),
        ("Build user interfaces for web products", "Work with designers on the design system", "Improve performance and accessibility"),
        ("Разработка интерфейсов веб-продуктов", "Работа с дизайнерами над дизайн-системой", "Улучшение производительности и доступности"),
        (2, 3, 4),
    ),
    Archetype(
        "frontend_angular",
        (("Junior Angular Developer", ("angular",)), ("Angular Developer", ("angular",)), ("Senior Angular Engineer", ("angular",))),
        (("Junior Angular-разработчик", ("angular",)), ("Angular-разработчик", ("angular",)), ("Ведущий Angular-разработчик", ("angular",))),
        ("typescript", "angular", "rxjs", "html", "css"),
        ("ngrx", "sass", "jest", "rest", "git", "mui", "webpack"),
        ("react", "nodejs", "cypress", "playwright"),
        ("Develop enterprise web applications", "Build reusable components", "Write unit and integration tests"),
        ("Разработка корпоративных веб-приложений", "Создание переиспользуемых компонентов", "Написание модульных и интеграционных тестов"),
        (2, 3, 4),
    ),
    Archetype(
        "fullstack_js",
        (("Junior Full-Stack Developer", ()), ("Full-Stack Developer (Node.js/React)", ("nodejs", "react")), ("Senior Full-Stack Engineer", ())),
        (("Junior fullstack-разработчик", ()), ("Fullstack-разработчик (Node.js, React)", ("nodejs", "react")), ("Senior fullstack-разработчик", ())),
        ("javascript", "typescript", "nodejs", "react"),
        (("express", "nestjs"), ("postgresql", "mongodb"), "docker", "rest", "nextjs", "redis", "git", "jest"),
        ("graphql", "aws", "kubernetes", "websocket"),
        ("Build features end to end, from API to UI", "Own services in production", "Mentor junior colleagues"),
        ("Разработка функциональности от API до интерфейса", "Ответственность за сервисы в продакшене", "Помощь младшим коллегам"),
        (2, 3, 4),
    ),
    Archetype(
        "data_analyst",
        (("Junior Data Analyst", ()), ("Data Analyst", ()), ("Senior Product Analyst", ())),
        (("Младший аналитик данных", ()), ("Аналитик данных", ()), ("Ведущий продуктовый аналитик", ())),
        ("sql", "excel", "python", "pandas"),
        (("powerbi", "tableau"), "statistics", "ab_testing", "product_analytics", "clickhouse", "postgresql", "jupyter", "superset"),
        ("airflow", "r", "spark"),
        ("Analyse product metrics and user behaviour", "Run and evaluate A/B tests", "Build dashboards for the business"),
        ("Анализ продуктовых метрик и поведения пользователей", "Проведение и оценка A/B-тестов", "Построение дашбордов для бизнеса"),
        (2, 2, 3),
    ),
    Archetype(
        "data_scientist",
        (("Junior Data Scientist", ()), ("Data Scientist", ()), ("Senior Data Scientist", ())),
        (("Junior data scientist", ()), ("Data scientist", ()), ("Ведущий data scientist", ())),
        ("python", "ml", "pandas", "numpy", "sklearn"),
        (("pytorch", "tensorflow"), "statistics", "sql", "jupyter", "gbm", "nlp", "computer_vision", "docker", "mlops"),
        ("spark", "airflow", "llm", "rag", "kubernetes"),
        ("Build and validate machine learning models", "Prepare features and datasets", "Present results to stakeholders"),
        ("Построение и валидация моделей машинного обучения", "Подготовка признаков и датасетов", "Презентация результатов заказчикам"),
        (3, 3, 4),
    ),
    Archetype(
        "llm_engineer",
        (("Junior AI Engineer", ()), ("LLM Engineer", ("llm",)), ("Senior AI Engineer (LLM)", ("llm",))),
        (("Junior AI-инженер", ()), ("LLM-инженер", ("llm",)), ("Ведущий AI-инженер (LLM)", ("llm",))),
        ("python", "llm", "rag", "embeddings"),
        ("langchain", "fastapi", "docker", "pytorch", "hf_transformers", "vector_db", "faiss", "agents", "postgresql", "kubernetes"),
        ("mlops", "ocr", "nlp", "go"),
        ("Build retrieval-augmented assistants over company documents", "Evaluate answer quality", "Ship AI features to production"),
        ("Разработка ассистентов на основе поиска по документам компании", "Оценка качества ответов", "Вывод AI-функций в продакшен"),
        (3, 4, 4),
    ),
    Archetype(
        "devops",
        (("Junior DevOps Engineer", ()), ("DevOps Engineer", ()), ("Senior SRE", ())),
        (("Junior DevOps-инженер", ()), ("DevOps-инженер", ()), ("Ведущий SRE-инженер", ())),
        ("linux", "docker", "kubernetes", "cicd"),
        ("terraform", "ansible", "prometheus", "grafana", "helm", ("aws", "gcp", "yandex_cloud"), "bash", ("gitlab_ci", "github_actions"), "nginx", "python", "elk"),
        ("go", "observability", "postgresql", "kafka"),
        ("Run and improve the Kubernetes platform", "Automate delivery pipelines", "Own monitoring and incident response"),
        ("Поддержка и развитие платформы на Kubernetes", "Автоматизация конвейеров поставки", "Мониторинг и разбор инцидентов"),
        (2, 3, 3),
    ),
    Archetype(
        "qa_automation",
        (("Junior QA Engineer", ()), ("QA Automation Engineer", ()), ("Senior QA Automation Engineer", ())),
        (("Junior QA-инженер", ()), ("Инженер по автоматизации тестирования", ("e2e_testing",)), ("Ведущий QA-инженер (автоматизация)", ())),
        ("e2e_testing", ("python", "java", "javascript"), ("selenium", "playwright", "cypress")),
        (("pytest", "junit", "jest"), "postman", "sql", "allure", "manual_testing", "cicd", "load_testing", "git", "rest"),
        ("docker", "kubernetes"),
        ("Automate regression tests", "Design test strategies with developers", "Keep the test pipeline green"),
        ("Автоматизация регрессионных тестов", "Разработка стратегии тестирования вместе с разработчиками", "Поддержка тестового конвейера"),
        (2, 2, 3),
    ),
    Archetype(
        "mobile",
        (("Junior Mobile Developer", ()), ("Mobile Developer", ()), ("Senior Mobile Engineer", ())),
        (("Junior мобильный разработчик", ()), ("Мобильный разработчик", ()), ("Ведущий мобильный разработчик", ())),
        (("kotlin", "swift"), ("android", "ios")),
        (("jetpack_compose", "swiftui"), "rest", "git", "unit_testing", "cicd", ("flutter", "react_native")),
        ("graphql", "websocket"),
        ("Build native mobile apps", "Work on offline mode and performance", "Release to the app stores"),
        ("Разработка нативных мобильных приложений", "Работа над офлайн-режимом и производительностью", "Публикация в магазинах приложений"),
        (2, 3, 3),
    ),
    Archetype(
        "product_manager",
        (("Associate Product Manager", ("product_management",)), ("Product Manager", ("product_management",)), ("Senior Product Manager", ("product_management",))),
        (("Младший продакт-менеджер", ()), ("Продакт-менеджер", ()), ("Ведущий продакт-менеджер", ())),
        ("product_management", "product_analytics"),
        ("agile", "scrum", "jira", "sql", "ux", "stakeholder_management", "requirements", "figma", "ab_testing"),
        ("python", "excel", "project_management"),
        ("Own the product roadmap and priorities", "Talk to users and define problems", "Work with engineering and design"),
        ("Управление приоритетами продукта", "Общение с пользователями и постановка задач", "Работа с разработкой и дизайном"),
        (2, 3, 4),
    ),
    Archetype(
        "designer",
        (("Junior Product Designer", ()), ("Product Designer", ()), ("Senior UX/UI Designer", ("ui_design",))),
        (("Младший дизайнер интерфейсов", ()), ("Продуктовый дизайнер", ()), ("Ведущий UX/UI-дизайнер", ("ui_design",))),
        ("figma", "ui_design", "ux"),
        ("prototyping", "design_systems", "adobe", "a11y", "html", "css"),
        ("threejs", "product_analytics"),
        ("Design flows and interfaces", "Run usability tests", "Maintain the design system"),
        ("Проектирование сценариев и интерфейсов", "Проведение юзабилити-тестов", "Развитие дизайн-системы"),
        (2, 3, 3),
    ),
)  # fmt: skip

BY_ID = {archetype.id: archetype for archetype in ARCHETYPES}

# neighbours share skills, so their candidates are plausible but weaker matches
NEIGHBOURS = {
    "python_backend": ("llm_engineer", "data_scientist", "devops"),
    "java_backend": ("python_backend", "fullstack_js"),
    "frontend_react": ("fullstack_js", "frontend_angular", "designer"),
    "frontend_angular": ("frontend_react", "fullstack_js"),
    "fullstack_js": ("frontend_react", "python_backend"),
    "data_analyst": ("data_scientist", "product_manager"),
    "data_scientist": ("llm_engineer", "data_analyst"),
    "llm_engineer": ("data_scientist", "python_backend"),
    "devops": ("python_backend", "java_backend"),
    "qa_automation": ("python_backend", "frontend_react"),
    "mobile": ("frontend_react", "fullstack_js"),
    "product_manager": ("data_analyst", "designer"),
    "designer": ("frontend_react", "product_manager"),
}
