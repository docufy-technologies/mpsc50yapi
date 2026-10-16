from datetime import datetime
from uuid import UUID

from sqlmodel import Session, col, select

from app.models import Alum
from app.schemas.referrals import ReferredAlumInformation
from app.services.referrals import counts_as_referral


def referrals_for(
    database_session: Session, alum_uuid: UUID
) -> tuple[list[ReferredAlumInformation], list[datetime]]:
    rows = database_session.exec(
        select(Alum)
        .where(Alum.referred_by_alum_uuid == alum_uuid)
        .order_by(col(Alum.registered_at), col(Alum.uuid))
    ).all()
    referrals = [
        ReferredAlumInformation(
            uuid=alum.uuid, full_name=alum.full_name, status=alum.status
        )
        for alum in rows
    ]
    qualifying_dates = [
        alum.registered_at
        for alum in rows
        if counts_as_referral(alum)
    ]
    return referrals, qualifying_dates
