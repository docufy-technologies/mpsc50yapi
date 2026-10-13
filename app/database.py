from sqlmodel import Session, create_engine

from .settings import settings

engine = create_engine(settings.database_uri)


def get_database_session():
    session = Session(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
