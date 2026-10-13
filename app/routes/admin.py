from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlmodel import case, col, func, select

from app.dependencies import Admin, DBSession
from app.models import (
    Acquaintance,
    Address,
    Alumna,
    AlumniPayment,
    AlumniProfile,
    Payment,
    WorkProfile,
)
from app.schemas.alumni import (
    AcquaintanceInformation,
    AddressInformation,
    AlumnaInformation,
    AlumniProfileInformation,
    WorkProfileInformation,
)
from app.schemas.authentication import AdminLogin, AdminSession
from app.schemas.payment import AdminPaymentSummary
from app.services.administration import encode_admin_token, is_valid_admin_secret
from app.services.token import ADMIN_TOKEN_TTL_SECONDS
from app.settings import settings
from app.schemas.referrals import ReferralDrilldown, ReferralLeaderboardEntry
from app.services.referral_queries import referrals_for
from app.types import AccountStatus

router = APIRouter(prefix="/admin", tags=["Administration Routes"])


@router.post(
    "/login",
    response_model=AdminSession,
    summary="Exchange the admin secret for an admin session cookie",
)
def admin_login(credentials: AdminLogin) -> JSONResponse:
    """Sign the admin panel in.

    Returns a dedicated httpOnly cookie rather than telling the browser to store
    the secret: anything in localStorage is readable by any script on the origin.
    """
    if not is_valid_admin_secret(credentials.admin_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
        )

    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content=AdminSession(
            expires_in=ADMIN_TOKEN_TTL_SECONDS
        ).model_dump(),
    )
    response.set_cookie(
        **settings.admin_token_config(encode_admin_token(), ADMIN_TOKEN_TTL_SECONDS)
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
    response.delete_cookie(**settings.delete_cookie_config(settings.admin_token_name))
    return response


@router.get(
    "/session",
    summary="Confirm the admin session is still valid",
)
def admin_session(_: Admin) -> dict[str, bool]:
    """Lets the panel choose between the login form and the table."""
    return {"authenticated": True}


def _payment_summary(
    alumna_uuid: UUID, database_session: DBSession
) -> AdminPaymentSummary:
    """Payment state for one alumna, in one query to avoid N+1 on the listing.

    Ordered by status before time: a settled payment takes its timestamp from the
    gateway while a failed one keeps its creation time, so ordering on time alone
    can hide a success behind a later failure.
    """
    payment = database_session.scalar(
        select(Payment)
        .join(AlumniPayment, col(AlumniPayment.payment_uuid) == col(Payment.uuid))
        .where(col(AlumniPayment.alumna_uuid) == alumna_uuid)
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
        latest_status=payment.status,
        amount=payment.amount,
        transaction_reference=payment.transaction_reference,
        paid_at=payment.paid_at,
    )


@router.get("/referrals", response_model=list[ReferralLeaderboardEntry])
def referral_leaderboard(
    _: AdminSecret, database_session: DBSession
) -> list[ReferralLeaderboardEntry]:
    profiles = database_session.scalars(
        select(AlumniProfile).where(AlumniProfile.alumna_uuid.is_not(None))
    ).all()
    entries = []
    for profile in profiles:
        alumna = database_session.get(Alumna, profile.alumna_uuid)
        if not alumna:
            continue
        _, dates = referrals_for(database_session, alumna.uuid)
        entries.append(
            ReferralLeaderboardEntry(
                alumna_uuid=alumna.uuid,
                full_name=alumna.full_name,
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
            str(entry.alumna_uuid),
        ),
    )


@router.get("/referrals/{alumna_uuid}", response_model=ReferralDrilldown)
def referral_drilldown(
    alumna_uuid: UUID, _: AdminSecret, database_session: DBSession
) -> ReferralDrilldown:
    alumna = database_session.get(Alumna, alumna_uuid)
    profile = database_session.scalar(
        select(AlumniProfile).where(AlumniProfile.alumna_uuid == alumna_uuid)
    )
    if not alumna or not profile:
        raise HTTPException(status_code=404, detail="Alumna not found")
    referrals, dates = referrals_for(database_session, alumna_uuid)
    return ReferralDrilldown(
        alumna_uuid=alumna.uuid,
        full_name=alumna.full_name,
        referral_code=profile.reg_code,
        referral_count=len(dates),
        earliest_qualifying_referral=min(dates) if dates else None,
        referrals=referrals,
    )


def _full_information(alumna: Alumna, database_session: DBSession) -> AlumnaInformation:
    """Admin-side projection: includes status and profile even when incomplete."""
    profile = database_session.scalar(
        select(AlumniProfile).where(AlumniProfile.alumna_uuid == alumna.uuid)
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
                WorkProfileInformation.model_validate(work_profile, from_attributes=True)
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
        select(Acquaintance).where(Acquaintance.alumna_uuid == alumna.uuid)
    ).all()

    return AlumnaInformation(
        uuid=alumna.uuid,
        full_name=alumna.full_name,
        email=alumna.email,
        phone_number=alumna.phone_number,
        status=alumna.status,
        created_at=alumna.created_at,
        profile=profile_information,
        payment=_payment_summary(alumna.uuid, database_session),
        acquaintances=[
            AcquaintanceInformation.model_validate(a, from_attributes=True)
            for a in acquaintances
        ],
    )

@router.get(
    "/alumnae",
    response_model=list[AlumnaInformation],
    summary="List registered alumnae, optionally filtered by account status",
)
def list_alumnae(
    _: Admin,
    database_session: DBSession,
    status_filter: AccountStatus | None = Query(
        default=None, alias="status", description="pending | confirmed | cancelled"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    statement = select(Alumna)
    if status_filter:
        statement = statement.where(Alumna.status == status_filter)

    alumnae = database_session.scalars(
        statement.order_by(col(Alumna.created_at).desc()).offset(offset).limit(limit)
    ).all()

    return [_full_information(alumna, database_session) for alumna in alumnae]


@router.get(
    "/alumnae/counts",
    summary="Count alumnae grouped by account status",
)
def count_alumnae(_: Admin, database_session: DBSession) -> dict[str, int]:
    # col() so SQLAlchemy reads this as an expression, not an attribute.
    rows = database_session.execute(
        select(col(Alumna.status), func.count()).group_by(col(Alumna.status))
    ).all()

    counts = {"pending": 0, "confirmed": 0, "cancelled": 0}
    for account_status, total in rows:
        counts[str(account_status)] = int(total)

    return counts


@router.patch(
    "/alumnae/{alumna_uuid}/status",
    response_model=AlumnaInformation,
    summary="Approve, cancel or reactivate an alumna account",
)
def update_alumna_status(
    alumna_uuid: UUID,
    new_status: AccountStatus,
    _: Admin,
    database_session: DBSession,
):
    alumna = database_session.get(Alumna, alumna_uuid)
    if not alumna:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alumna not found"
        )

    alumna.status = new_status
    database_session.add(alumna)
    database_session.commit()
    database_session.refresh(alumna)

    return _full_information(alumna, database_session)
