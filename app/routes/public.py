from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import func, select

from app.database import DBSession
from app.settings import settings
from app.models import Alumna, AlumniProfile, EventDeadline
from app.services.deadlines import deadline_is_open

router = APIRouter(prefix="/public", tags=["Public Routes"])


class EventInformation(BaseModel):
    name: str
    subtitle: str
    established_year: int
    celebration_year: int
    registration_deadline: str
    event_date: str
    venue: str
    participation_fee_bdt: int


class PublicStatistics(BaseModel):
    confirmed_alumnae: int
    total_registrations: int
    batch_years_covered: int


class PublicDeadline(BaseModel):
    key: str
    label: str
    deadline_at: datetime
    is_extended: bool
    is_open: bool


EVENT_INFORMATION = EventInformation(
    name="MPSC Golden Jubilee",
    subtitle="Celebrating 50 years of Mohammadpur Preparatory School & College",
    established_year=1976,
    celebration_year=2026,
    registration_deadline="2026-11-10T23:59:59",
    event_date="2026-12-20",
    venue="Mohammadpur Preparatory School & College, Mohammadpur, Dhaka",
    # Overridden per request from settings.event_fee_bdt, the amount charged.
    participation_fee_bdt=0,
)


@router.get("/event", response_model=EventInformation, summary="Static event information")
def get_event_information() -> EventInformation:
    return EVENT_INFORMATION.model_copy(
        update={"participation_fee_bdt": settings.event_fee_bdt}
    )


@router.get(
    "/statistics",
    response_model=PublicStatistics,
    summary="Aggregate participation counts (no personally identifying data)",
)
def get_statistics(database_session: DBSession) -> PublicStatistics:
    confirmed = database_session.scalar(
        select(func.count()).select_from(Alumna).where(Alumna.status == "confirmed")
    )
    total = database_session.scalar(select(func.count()).select_from(Alumna))

    distinct_batches = database_session.scalar(
        select(func.count(func.distinct(AlumniProfile.batch_year)))
    )

    return PublicStatistics(
        confirmed_alumnae=int(confirmed or 0),
        total_registrations=int(total or 0),
        batch_years_covered=int(distinct_batches or 0),
    )


@router.get("/deadlines", response_model=list[PublicDeadline])
def get_deadlines(database_session: DBSession) -> list[PublicDeadline]:
    deadlines = database_session.scalars(select(EventDeadline).order_by(EventDeadline.key)).all()
    return [
        PublicDeadline(
            key=item.key,
            label=item.label,
            deadline_at=item.deadline_at,
            is_extended=item.is_extended,
            is_open=deadline_is_open(item),
        )
        for item in deadlines
    ]
