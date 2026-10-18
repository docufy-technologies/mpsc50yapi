from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import SQLModel

from app.routes import admin, auth, involve, media, payment, public

DESCRIPTION = """
Backend for the MPSC 50 Years Golden Jubilee celebration.

* `/auth/*` registration, login and profile management
* `/media/*` media uploads and assets
* `/admin/*` admin-only endpoints
* `/payments/*` SSLCommerz checkout
* `/public/*` unauthenticated event information
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    from app import models  # type:ignore  # noqa: F401
    from app.database import engine

    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(
    title="MPSC 50 Years Alumni API",
    version="1.0.0",
    description=DESCRIPTION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "https://mpsc.docufybd.com",
        "http://mpsc.docufybd.com",
        "https://mpsc50years.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(media.router)
app.include_router(admin.router)
app.include_router(payment.router)
app.include_router(public.router)
app.include_router(involve.router)

# Mount media directory for static file access (ensuring directory exists)
Path("media").mkdir(parents=True, exist_ok=True)
app.mount("/media/assets", StaticFiles(directory="media"), name="media")


@app.get("/", tags=["Health"])
def health_check():
    return {"message": "MPSC 50 Years Alumni API is running"}
