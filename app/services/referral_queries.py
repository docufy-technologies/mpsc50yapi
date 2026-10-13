from datetime import datetime
from uuid import UUID

from sqlmodel import Session, col, select

from app.models import Alum, AlumniProfile
from app.schemas.referrals import ReferredAlumInformation
from app.services.referrals import counts_as_referral


def referrals_for(
    database_session: Session, alum_uuid: UUID
) -> tuple[list[ReferredAlumInformation], list[datetime]]:
    rows = database_session.execute(
        select(Alum, AlumniProfile)
        .join(AlumniProfile, AlumniProfile.alum_uuid == Alum.uuid)
        .where(AlumniProfile.referred_by_alum_uuid == alum_uuid)
        .order_by(col(AlumniProfile.registered_at), col(Alum.uuid))
    ).all()
    referrals = [
        ReferredAlumInformation(
            uuid=alum.uuid, full_name=alum.full_name, status=alum.status
        )
        for alum, _ in rows
    ]
    qualifying_dates = [
        profile.registered_at
        for alum, profile in rows
        if counts_as_referral(alum)
    ]
    return referrals, qualifying_dates
