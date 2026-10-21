from fastapi import APIRouter
from sqlmodel import func, select

from app.database import DBSession
from app.models import Alum
from app.schemas.public import EventInformation, PublicDeadline, PublicStatistics
from app.services.deadlines import deadline_is_open
from app.settings import settings

router = APIRouter(prefix="/public", tags=["Public Routes"])


EVENT_INFORMATION = EventInformation(
    name="MPSC Golden Jubilee",
    subtitle="Celebrating 50 years of Mohammadpur Preparatory School & College",
    established_year=1976,
    celebration_year=2026,
    registration_deadline=settings.event_deadlines["registration"].isoformat(),
    event_date="2026-12-20",
    venue="Mohammadpur Preparatory School & College, Mohammadpur, Dhaka",
    # Overridden per request from settings.event_fee_bdt, the amount charged.
    participation_fee_bdt=settings.event_fee_bdt,
)


@router.get(
    "/event", response_model=EventInformation, summary="Static event information"
)
def get_event_information() -> EventInformation:
    return EVENT_INFORMATION


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
        select(func.count(func.distinct(Alum.batch_year)))
    )

    return PublicStatistics(
        confirmed_alumni=int(confirmed or 0),
        total_registrations=int(total or 0),
        batch_years_covered=int(distinct_batches or 0),
    )


@router.get("/deadlines", response_model=list[PublicDeadline])
def get_deadlines() -> list[PublicDeadline]:
    labels = {
        "registration": "Alumni registration",
        "stall": "Stall applications",
        "sponsor": "Sponsor offers",
        "subcommittee": "Subcommittee applications",
        "openmic": "Open mic entries",
    }
    return [
        PublicDeadline(
            key=key,
            label=labels[key],
            deadline_at=deadline,
            is_extended=False,
            is_open=deadline_is_open(deadline),
        )
        for key, deadline in sorted(settings.event_deadlines.items())
    ]
