from fastapi import APIRouter
from sqlmodel import func, select

from app.dependencies import DBSession
from app.models import Alum, AlumniProfile, EventDeadline
from app.schemas.public import EventInformation, PublicDeadline, PublicStatistics
from app.services.deadlines import deadline_is_open
from app.settings import settings

router = APIRouter(prefix="/public", tags=["Public Routes"])


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


@router.get(
    "/event", response_model=EventInformation, summary="Static event information"
)
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
        select(func.count()).select_from(Alum).where(Alum.status == "confirmed")
    )
    total = database_session.scalar(select(func.count()).select_from(Alum))

    distinct_batches = database_session.scalar(
        select(func.count(func.distinct(AlumniProfile.batch_year)))
    )

    return PublicStatistics(
        confirmed_alumni=int(confirmed or 0),
        total_registrations=int(total or 0),
        batch_years_covered=int(distinct_batches or 0),
    )


@router.get("/deadlines", response_model=list[PublicDeadline])
def get_deadlines(database_session: DBSession) -> list[PublicDeadline]:
    deadlines = database_session.scalars(
        select(EventDeadline).order_by(EventDeadline.key)
    ).all()
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
