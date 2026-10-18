from sqlmodel import SQLModel

from app import models  # noqa #type:ignore
from app.database import engine

SQLModel.metadata.create_all(engine)
