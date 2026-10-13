from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlmodel import col, select

from app.constants import SUBCOMMITTEE_NAMES
from app.dependencies import CurrentAlum, DBSession
from app.helper import now
from app.models import (
    AlumniProfile,
    OpenMicEntry,
    SponsorOffer,
    StallApplication,
    SubcommitteeApplication,
)
from app.schemas.involve import (
    OpenMicEntryInformation,
    OpenMicEntryInput,
    SponsorOfferInformation,
    SponsorOfferInput,
    StallApplicationInformation,
    StallApplicationInput,
    SubcommitteeApplicationInformation,
    SubcommitteeApplicationInput,
)
from app.schemas.referrals import MyReferralsInformation
from app.services.deadlines import ensure_open
from app.services.referral_queries import referrals_for
from app.settings import settings

router = APIRouter(prefix="/involve", tags=["Get Involved"])


@router.get("/referrals/me", response_model=MyReferralsInformation)
def read_my_referrals(alum: CurrentAlum, database_session: DBSession):
    profile = database_session.scalar(
        select(AlumniProfile).where(AlumniProfile.alum_uuid == alum.uuid)
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Alum profile not found")
    referrals, qualifying_dates = referrals_for(database_session, alum.uuid)
    return MyReferralsInformation(
        referral_code=profile.reg_code,
        referral_count=len(qualifying_dates),
        referrals=referrals,
    )


@router.post(
    "/stall",
    status_code=status.HTTP_201_CREATED,
    response_model=StallApplicationInformation,
)
def create_stall_application(
    data: StallApplicationInput, alum: CurrentAlum, database_session: DBSession
) -> StallApplication:
    ensure_open("stall", database_session, now=now)
    existing = database_session.scalar(
        select(StallApplication).where(StallApplication.alum_uuid == alum.uuid)
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A stall application already exists",
        )
    application = StallApplication(alum_uuid=alum.uuid, **data.model_dump())
    database_session.add(application)
    database_session.commit()
    database_session.refresh(application)
    return application


@router.get("/stall/me", response_model=StallApplicationInformation)
def read_my_stall_application(
    alum: CurrentAlum, database_session: DBSession
) -> StallApplication:
    application = database_session.scalar(
        select(StallApplication).where(StallApplication.alum_uuid == alum.uuid)
    )
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Stall application not found"
        )
    return application


@router.put("/stall/me", response_model=StallApplicationInformation)
def update_my_stall_application(
    data: StallApplicationInput, alum: CurrentAlum, database_session: DBSession
) -> StallApplication:
    ensure_open("stall", database_session, now=now)
    application = database_session.scalar(
        select(StallApplication).where(StallApplication.alum_uuid == alum.uuid)
    )
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Stall application not found"
        )
    if application.status == "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Approved stall applications can no longer be edited",
        )
    for field, value in data.model_dump().items():
        setattr(application, field, value)
    application.updated_at = now()
    database_session.add(application)
    database_session.commit()
    database_session.refresh(application)
    return application


@router.post(
    "/sponsor",
    status_code=status.HTTP_201_CREATED,
    response_model=SponsorOfferInformation,
)
def create_sponsor_offer(
    data: SponsorOfferInput, alum: CurrentAlum, database_session: DBSession
) -> SponsorOffer:
    ensure_open("sponsor", database_session, now=now)
    count = len(
        database_session.exec(
            select(SponsorOffer).where(SponsorOffer.alum_uuid == alum.uuid)
        ).all()
    )
    if count >= settings.sponsor_offer_limit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Sponsor offer limit reached"
        )
    offer = SponsorOffer(alum_uuid=alum.uuid, **data.model_dump())
    database_session.add(offer)
    database_session.commit()
    database_session.refresh(offer)
    return offer


@router.get("/sponsor/me", response_model=list[SponsorOfferInformation])
def read_my_sponsor_offers(
    alum: CurrentAlum, database_session: DBSession
) -> list[SponsorOffer]:
    return list(
        database_session.exec(
            select(SponsorOffer)
            .where(SponsorOffer.alum_uuid == alum.uuid)
            .order_by(col(SponsorOffer.created_at).desc())
        ).all()
    )


@router.get("/subcommittee/options", response_model=list[str])
def subcommittee_options() -> list[str]:
    return SUBCOMMITTEE_NAMES


@router.post(
    "/subcommittee",
    status_code=status.HTTP_201_CREATED,
    response_model=SubcommitteeApplicationInformation,
)
def create_subcommittee_application(
    data: SubcommitteeApplicationInput,
    alum: CurrentAlum,
    database_session: DBSession,
) -> SubcommitteeApplication:
    ensure_open("subcommittee", database_session, now=now)
    existing = database_session.scalar(
        select(SubcommitteeApplication).where(
            SubcommitteeApplication.alum_uuid == alum.uuid
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A sub-committee application already exists",
        )

    application = SubcommitteeApplication(alum_uuid=alum.uuid, **data.model_dump())
    database_session.add(application)
    database_session.commit()
    database_session.refresh(application)
    return application


@router.get("/subcommittee/me", response_model=SubcommitteeApplicationInformation)
def read_my_subcommittee_application(
    alum: CurrentAlum, database_session: DBSession
) -> SubcommitteeApplication:
    application = database_session.scalar(
        select(SubcommitteeApplication).where(
            SubcommitteeApplication.alum_uuid == alum.uuid
        )
    )
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sub-committee application not found",
        )
    return application


@router.put("/subcommittee/me", response_model=SubcommitteeApplicationInformation)
def update_my_subcommittee_application(
    data: SubcommitteeApplicationInput,
    alum: CurrentAlum,
    database_session: DBSession,
) -> SubcommitteeApplication:
    ensure_open("subcommittee", database_session, now=now)
    application = database_session.scalar(
        select(SubcommitteeApplication).where(
            SubcommitteeApplication.alum_uuid == alum.uuid
        )
    )
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sub-committee application not found",
        )
    if application.status != "submitted":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This application can no longer be edited",
        )

    for field, value in data.model_dump().items():
        setattr(application, field, value)
    application.updated_at = now()
    database_session.add(application)
    database_session.commit()
    database_session.refresh(application)
    return application


@router.post(
    "/openmic",
    status_code=status.HTTP_201_CREATED,
    response_model=OpenMicEntryInformation,
)
def create_openmic_entry(
    data: OpenMicEntryInput, alum: CurrentAlum, database_session: DBSession
) -> OpenMicEntry:
    ensure_open("openmic", database_session, now=now)
    count = len(
        database_session.exec(
            select(OpenMicEntry).where(OpenMicEntry.alum_uuid == alum.uuid)
        ).all()
    )
    if count >= settings.openmic_entry_limit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Open mic entry limit reached",
        )
    entry = OpenMicEntry(alum_uuid=alum.uuid, **data.model_dump())
    database_session.add(entry)
    database_session.commit()
    database_session.refresh(entry)
    return entry


@router.get("/openmic/me", response_model=list[OpenMicEntryInformation])
def read_my_openmic_entries(
    alum: CurrentAlum, database_session: DBSession
) -> list[OpenMicEntry]:
    return list(
        database_session.exec(
            select(OpenMicEntry)
            .where(OpenMicEntry.alum_uuid == alum.uuid)
            .order_by(col(OpenMicEntry.created_at).desc())
        ).all()
    )


@router.put("/openmic/{entry_uuid}", response_model=OpenMicEntryInformation)
def update_my_openmic_entry(
    entry_uuid: UUID,
    data: OpenMicEntryInput,
    alum: CurrentAlum,
    database_session: DBSession,
) -> OpenMicEntry:
    ensure_open("openmic", database_session, now=now)
    entry = database_session.scalar(
        select(OpenMicEntry).where(
            OpenMicEntry.uuid == entry_uuid,
            OpenMicEntry.alum_uuid == alum.uuid,
        )
    )
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Open mic entry not found",
        )
    for field, value in data.model_dump().items():
        setattr(entry, field, value)
    database_session.add(entry)
    database_session.commit()
    database_session.refresh(entry)
    return entry


@router.delete("/openmic/{entry_uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_openmic_entry(
    entry_uuid: UUID, alum: CurrentAlum, database_session: DBSession
) -> None:
    ensure_open("openmic", database_session, now=now)
    entry = database_session.scalar(
        select(OpenMicEntry).where(
            OpenMicEntry.uuid == entry_uuid,
            OpenMicEntry.alum_uuid == alum.uuid,
        )
    )
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Open mic entry not found",
        )
    database_session.delete(entry)
    database_session.commit()
