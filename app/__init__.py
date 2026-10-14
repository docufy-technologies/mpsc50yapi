from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel

from app.routes import admin, auth, involve, payment, public

DESCRIPTION = """
Backend for the MPSC 50 Years Golden Jubilee celebration.

* `/auth/*` registration, login and profile management
* `/admin/*` admin-only endpoints
* `/payments/*` SSLCommerz checkout
* `/public/*` unauthenticated event information
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    from app.database import engine
    from app.models import *  # noqa #type:ignore

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
        "https://mpsc50years.docufybd.com",
        "http://mpsc50years.docufybd.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(payment.router)
app.include_router(public.router)
app.include_router(involve.router)


@app.get("/", tags=["Health"])
def health_check():
    return {"message": "MPSC 50 Years Alumni API is running"}
