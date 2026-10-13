from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel

from app import models  # noqa: F401  (registers all tables)
from app.database import engine
from app.routes import admin, auth, involve, payment, public
from app.settings import settings

DESCRIPTION = """
Backend for the MPSC 50 Years Golden Jubilee celebration.

* `/auth/*` registration, login and profile management
* `/admin/*` account approval (requires the `X-Admin-Secret` header)
* `/payments/*` SSLCommerz checkout
* `/public/*` unauthenticated event information
"""


def _allowed_origins() -> list[str]:
    origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://mpsc50years.docufybd.com",
        "http://mpsc50years.docufybd.com",
    ]
    if settings.dev_mode:
        # Allow any localhost port so parallel dev servers (5173, 4173, ...) work.
        origins.extend(f"http://localhost:{port}" for port in range(3000, 3020))
        origins.extend(f"http://127.0.0.1:{port}" for port in range(3000, 3020))
    return origins


def create_app(*, create_tables: bool = True) -> FastAPI:
    """Application factory. Tests pass create_tables=False and override the
    database session with an in-memory engine."""

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        # Only safe on SQLite. Use Alembic migrations for real databases;
        # see alembic/ and `alembic upgrade head`.
        SQLModel.metadata.create_all(bind=engine)
        yield

    application = FastAPI(
        title="MPSC 50 Years Alumni API",
        version="1.0.0",
        description=DESCRIPTION,
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_origin_regex=(
            r"http://(localhost|127\.0\.0\.1)(:\d+)?" if settings.dev_mode else None
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(auth.router)
    application.include_router(admin.router)
    application.include_router(payment.router)
    application.include_router(public.router)
    application.include_router(involve.router)

    @application.get("/", tags=["Health"])
    def health_check():
        return {"message": "MPSC 50 Years Alumni API is running"}

    return application


app = create_app()
