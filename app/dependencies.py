from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from app.database import get_database_session
from app.models import Admin, Alum

DBSession = Annotated[Session, Depends(get_database_session)]

from app.services.administration import get_current_admin
from app.services.authentication import get_current_alum

CurrentAlum = Annotated[Alum, Depends(get_current_alum)]
CurrentAdmin = Annotated[Admin, Depends(get_current_admin)]

__all__ = ["CurrentAdmin", "CurrentAlum", "DBSession"]
