from datetime import UTC, datetime

from fastapi import HTTPException, status

from app.helper import now as current_time
from app.settings import DeadlineKey, settings


def ensure_open(key: DeadlineKey) -> datetime:
    try:
        deadline = settings.event_deadlines[key]
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deadline not found")

    current = current_time()
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    cutoff = deadline
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=UTC)
    if current > cutoff:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Submissions closed",
        )
    return deadline


def deadline_is_open(deadline: datetime, now: datetime | None = None) -> bool:
    current = now or current_time()
    cutoff = deadline
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=UTC)
    return current <= cutoff
