"""The HTTP API.

uvicorn clearhire.api.app:create_app --factory
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from clearhire import __version__
from clearhire.api.routes import applications, auth, candidates, insights, public, vacancies
from clearhire.config import Settings, get_settings
from clearhire.events import Events
from clearhire.tasks import broker, build_services

REQUESTS = Counter("clearhire_http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("clearhire_http_request_seconds", "HTTP request latency", ["route"],
                    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))  # fmt: skip
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.check_production()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.services = build_services(settings)
        app.state.events = Events(settings.redis_url)
        if not broker.is_worker_process:
            await broker.startup()
        yield
        await broker.shutdown()
        await app.state.events.close()

    app = FastAPI(
        title="Clearhire",
        version=__version__,
        summary="Explainable AI recruiting: requirement-level matching with evidence, blind screening and an audit trail.",
        lifespan=lifespan,
    )
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])  # fmt: skip

    @app.middleware("http")
    async def observe(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        route = getattr(request.scope.get("route"), "path", "unmatched")  # templates, never raw ids
        REQUESTS.labels(request.method, route, str(response.status_code)).inc()
        LATENCY.labels(route).observe(time.perf_counter() - started)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    for module in (auth, vacancies, candidates, applications, insights, public):
        app.include_router(module.router)

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
