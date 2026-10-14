from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import Session, select


def now() -> datetime:
    return datetime.now(UTC)


def generate_reg_code(session: Session) -> str:
    """Generate a 12-char hex registration code, guaranteed unique in the DB."""
    from app.models import AlumniProfile

    while True:
        code = uuid4().hex[:12].upper()
        existing = session.scalar(
            select(AlumniProfile).where(AlumniProfile.reg_code == code)
        )
        if not existing:
            return code
