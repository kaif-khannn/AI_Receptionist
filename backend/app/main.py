"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.core.config import Settings, get_settings
from app.core.db import Database
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.middleware.request_context import REQUEST_ID_HEADER, RequestContextMiddleware
from app.routers import auth, business, catalogue, engineers, health
from app.services.auth import AuthService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn.get_secret_value(),
            environment=settings.environment,
            release=__version__,
            send_default_pii=False,  # callers' personal data must not leave our system
            traces_sample_rate=0.1,
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.db = None
        app.state.auth = None
        if settings.database_url is not None:
            db = Database(settings)
            await db.assert_rls_enforced()
            app.state.db = db
            if settings.secret_key is not None:
                app.state.auth = AuthService(db, settings)
        try:
            yield
        finally:
            if app.state.db is not None:
                await app.state.db.dispose()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(business.router)
    app.include_router(catalogue.router)
    app.include_router(engineers.router)
    return app


app = create_app()
