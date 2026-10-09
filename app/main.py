from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  (makes sure all tables are registered)
from .database import Base, engine
from .routers import auth, events, registrations


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)  # creates tables on first run
    yield


app = FastAPI(title="50 Years Alumni Event API", version="1.0.0", lifespan=lifespan)

# Allow your frontend to call this API. Replace "*" with your frontend URL when deploying.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(events.router)
app.include_router(registrations.router)


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "docs": "/docs"}
