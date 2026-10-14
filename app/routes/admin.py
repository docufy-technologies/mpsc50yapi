from typing import cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlmodel import case, col, func, select

from app.dependencies import CurrentAdmin, DBSession
from app.models import (
    Acquaintance,
    Address,
    Admin,
    Alum,
    AlumniPayment,
    AlumniProfile,
    Payment,
    WorkProfile,
)
from app.schemas.alumni import (
    AcquaintanceInformation,
    AddressInformation,
    AlumInformation,
    AlumniProfileInformation,
    WorkProfileInformation,
)
from app.schemas.auth import AdminInfo, AdminLogin, AdminSession
from app.schemas.payment import AdminPaymentSummary
from app.schemas.referrals import ReferralDrillDown, ReferralLeaderboardEntry
from app.services.admin import encode_admin_token
from app.services.auth import verify_password
from app.services.referral_queries import referrals_for
from app.services.token import ADMIN_TOKEN_TTL_SECONDS
from app.settings import settings
from app.types import AccountStatus, PaymentStatus

router = APIRouter(prefix="/admin", tags=["Administration Routes"])


@router.post(
    "/login",
    response_model=AdminSession,
    summary="Log an admin in with email + password",
)
def admin_login(credentials: AdminLogin, database_session: DBSession) -> JSONResponse:
    admin = database_session.scalar(
        select(Admin).where(Admin.email == credentials.email.lower())
    )
    if (
        not admin
        or not admin.is_active
        or not verify_password(credentials.password, admin.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
        )

    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content=AdminSession(expires_in=ADMIN_TOKEN_TTL_SECONDS).model_dump(),
    )
    response.set_cookie(
        **settings.admin_access_token_config(
            encode_admin_token(admin.uuid), ADMIN_TOKEN_TTL_SECONDS
        )
    )
    return response


@router.post(
    "/logout",
    summary="Clear the admin session cookie",
)
def admin_logout() -> JSONResponse:
    response = JSONResponse(
        status_code=status.HTTP_200_OK, content={"message": "Admin logged out"}
    )
    response.delete_cookie(
        **settings.delete_cookie_config(settings.admin_access_token_name)
    )
    return response


@router.get(
    "/session",
    summary="Confirm the admin session is still valid",
)
def admin_session(_: CurrentAdmin) -> dict[str, bool]:
    return {"authenticated": True}


@router.get(
    "/me",
    response_model=AdminInfo,
    summary="Get the current admin's information",
)
def get_admin_information(admin: CurrentAdmin):
    return AdminInfo(
        uuid=admin.uuid,
        email=admin.email,
        is_active=admin.is_active,
        created_at=admin.created_at,
    )


def _payment_summary(
    alum_uuid: UUID, database_session: DBSession
) -> AdminPaymentSummary:
    """Payment state for one alum, in one query to avoid N+1 on the listing.

    Ordered by status before time: a settled payment takes its timestamp from the
    gateway while a failed one keeps its creation time, so ordering on time alone
    can hide a success behind a later failure.
    """
    payment = database_session.scalar(
        select(Payment)
        .join(AlumniPayment, col(AlumniPayment.payment_uuid) == col(Payment.uuid))
        .where(col(AlumniPayment.alum_uuid) == alum_uuid)
        .order_by(
            # completed first, so a later failure cannot hide a success.
            case((col(Payment.status) == "completed", 0), else_=1),
            col(Payment.paid_at).desc(),
        )
        .limit(1)
    )

    if not payment:
        return AdminPaymentSummary()

    return AdminPaymentSummary(
        has_paid=payment.status == "completed",
        latest_status=cast(PaymentStatus, payment.status),
        amount=payment.amount,
        transaction_reference=payment.transaction_reference,
        paid_at=payment.paid_at,
    )


@router.get("/referrals", response_model=list[ReferralLeaderboardEntry])
def referral_leaderboard(
    _: CurrentAdmin, database_session: DBSession
) -> list[ReferralLeaderboardEntry]:
    profiles = database_session.scalars(
        select(AlumniProfile).where(col(AlumniProfile.alum_uuid).is_not(None))
    ).all()
    entries = []
    for profile in profiles:
        alum = database_session.get(Alum, profile.alum_uuid)
        if not alum:
            continue
        _referrals, dates = referrals_for(database_session, alum.uuid)
        entries.append(
            ReferralLeaderboardEntry(
                alum_uuid=alum.uuid,
                full_name=alum.full_name,
                referral_code=profile.reg_code,
                referral_count=len(dates),
                earliest_qualifying_referral=min(dates) if dates else None,
            )
        )
    return sorted(
        entries,
        key=lambda entry: (
            -entry.referral_count,
            (
                entry.earliest_qualifying_referral.timestamp()
                if entry.earliest_qualifying_referral
                else float("inf")
            ),
            str(entry.alum_uuid),
        ),
    )


@router.get("/referrals/{alum_uuid}", response_model=ReferralDrillDown)
def referral_drilldown(
    alum_uuid: UUID, _: CurrentAdmin, database_session: DBSession
) -> ReferralDrillDown:
    alum = database_session.get(Alum, alum_uuid)
    profile = database_session.scalar(
        select(AlumniProfile).where(AlumniProfile.alum_uuid == alum_uuid)
    )
    if not alum or not profile:
        raise HTTPException(status_code=404, detail="Alum not found")
    referrals, dates = referrals_for(database_session, alum_uuid)
    return ReferralDrillDown(
        alum_uuid=alum.uuid,
        full_name=alum.full_name,
        referral_code=profile.reg_code,
        referral_count=len(dates),
        earliest_qualifying_referral=min(dates) if dates else None,
        referrals=referrals,
    )


def _full_information(alum: Alum, database_session: DBSession) -> AlumInformation:
    """Admin-side projection: includes status and profile even when incomplete."""
    profile = database_session.scalar(
        select(AlumniProfile).where(AlumniProfile.alum_uuid == alum.uuid)
    )

    profile_information = None
    if profile:
        work_profile = (
            database_session.get(WorkProfile, profile.work_profile_uuid)
            if profile.work_profile_uuid
            else None
        )
        address = (
            database_session.get(Address, profile.address_uuid)
            if profile.address_uuid
            else None
        )

        profile_information = AlumniProfileInformation(
            uuid=profile.uuid,
            reg_code=profile.reg_code,
            student_id=profile.student_id,
            batch_year=profile.batch_year,
            tee_shirt_size=profile.tee_shirt_size,
            academic_group=profile.academic_group,
            registered_at=profile.registered_at,
            work_profile=(
                WorkProfileInformation.model_validate(
                    work_profile, from_attributes=True
                )
                if work_profile
                else None
            ),
            address=(
                AddressInformation.model_validate(address, from_attributes=True)
                if address
                else None
            ),
        )

    acquaintances = database_session.scalars(
        select(Acquaintance).where(Acquaintance.alum_uuid == alum.uuid)
    ).all()

    return AlumInformation(
        uuid=alum.uuid,
        full_name=alum.full_name,
        email=alum.email,
        phone_number=alum.phone_number,
        status=alum.status,
        created_at=alum.created_at,
        profile=profile_information,
        payment=_payment_summary(alum.uuid, database_session),
        acquaintances=[
            AcquaintanceInformation.model_validate(a, from_attributes=True)
            for a in acquaintances
        ],
    )


@router.get(
    "/alumni",
    response_model=list[AlumInformation],
    summary="List registered alumni, optionally filtered by account status",
)
def list_alumni(
    _: CurrentAdmin,
    database_session: DBSession,
    status_filter: AccountStatus | None = Query(
        default=None, alias="status", description="pending | confirmed | cancelled"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    statement = select(Alum)
    if status_filter:
        statement = statement.where(Alum.status == status_filter)

    alumni = database_session.scalars(
        statement.order_by(col(Alum.created_at).desc()).offset(offset).limit(limit)
    ).all()

    return [_full_information(alum, database_session) for alum in alumni]


@router.get(
    "/alumni/counts",
    summary="Count alumni grouped by account status",
)
def count_alumni(_: CurrentAdmin, database_session: DBSession) -> dict[str, int]:
    # col() so SQLAlchemy reads this as an expression, not an attribute.
    rows = database_session.execute(
        select(col(Alum.status), func.count()).group_by(col(Alum.status))
    ).all()

    counts = {"pending": 0, "confirmed": 0, "cancelled": 0}
    for account_status, total in rows:
        counts[str(account_status)] = int(total)

    return counts


@router.patch(
    "/alumni/{alum_uuid}/status",
    response_model=AlumInformation,
    summary="Approve, cancel or reactivate an alum account",
)
def update_alum_status(
    alum_uuid: UUID,
    new_status: AccountStatus,
    _: CurrentAdmin,
    database_session: DBSession,
):
    alum = database_session.get(Alum, alum_uuid)
    if not alum:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alum not found"
        )

    alum.status = new_status
    database_session.add(alum)
    database_session.commit()
    database_session.refresh(alum)

    return _full_information(alum, database_session)
