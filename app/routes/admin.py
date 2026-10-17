from typing import cast
from uuid import UUID

import jwt

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlmodel import case, col, func, select

from app.dependencies import CurrentAdmin, DBSession
from app.models import (
    Acquaintance,
    Admin,
    Alum,
    AlumniPayment,
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
from app.schemas.payment import PaymentSummary
from app.schemas.referrals import ReferralDrillDown, ReferralLeaderboardEntry
from datetime import timedelta, timezone
from uuid import uuid4

from app.helper import now
from app.models import AdminRefreshToken
from app.services.admin import encode_admin_token
from app.services.auth import verify_password
from app.services.referral_queries import referrals_for
from app.services.token import (
    decode_token,
    encode_refresh_token,
)
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

    admin_access_token = encode_admin_token(admin.uuid)

    refresh_jti = str(uuid4())
    refresh_token = encode_refresh_token(
        {"admin_uuid": str(admin.uuid), "admin": True}, refresh_jti,
        expiry_seconds=settings.admin_refresh_token_ttl_seconds,
    )
    database_session.add(
        AdminRefreshToken(
            admin_uuid=admin.uuid,
            refresh_token_jti=refresh_jti,
            created_at=now(),
            expires_at=now() + timedelta(seconds=settings.admin_refresh_token_ttl_seconds),
            revoked=False,
        )
    )
    database_session.commit()

    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content=AdminSession(expires_in=settings.admin_access_token_ttl_seconds).model_dump(),
    )
    response.set_cookie(
        **settings.admin_access_token_config(admin_access_token, settings.admin_access_token_ttl_seconds)
    )
    response.set_cookie(
        **settings.admin_refresh_token_config(refresh_token, settings.admin_refresh_token_ttl_seconds)
    )
    return response


@router.post(
    "/logout",
    summary="Clear the admin session cookie",
)
def admin_logout(request: Request, database_session: DBSession) -> JSONResponse:
    refresh_token = request.cookies.get(settings.admin_refresh_token_name)
    if refresh_token:
        try:
            payload = decode_token(refresh_token, verify_exp=False)
            jti = payload.get("jti")
            if jti:
                record = database_session.scalar(
                    select(AdminRefreshToken).where(
                        AdminRefreshToken.refresh_token_jti == jti
                    )
                )
                if record and not record.revoked:
                    record.revoked = True
                    database_session.add(record)
                    database_session.commit()
        except Exception:
            pass

    response = JSONResponse(
        status_code=status.HTTP_200_OK, content={"message": "Admin logged out"}
    )
    response.delete_cookie(
        **settings.delete_cookie_config(settings.admin_access_token_name)
    )
    response.delete_cookie(
        **settings.delete_cookie_config(settings.admin_refresh_token_name)
    )
    return response


@router.post(
    "/refresh-token",
    summary="Refresh the current admin's access token",
)
def refresh_admin_access_token(request: Request, database_session: DBSession):
    refresh_token = request.cookies.get(settings.admin_refresh_token_name)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token provided",
        )

    try:
        payload = decode_token(refresh_token)
        admin_uuid_str: str | None = payload.get("admin_uuid")
        jti: str | None = payload.get("jti")
        token_type: str | None = payload.get("type")

        if not admin_uuid_str or not jti or token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token payload",
            )

        admin = database_session.scalar(
            select(Admin).where(Admin.uuid == UUID(admin_uuid_str), Admin.is_active == True)
        )
        if not admin:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
            )

        db_refresh_token = database_session.scalar(
            select(AdminRefreshToken).where(
                AdminRefreshToken.admin_uuid == admin.uuid,
                AdminRefreshToken.refresh_token_jti == jti,
            )
        )
        if not db_refresh_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Refresh token not found"
            )

        if db_refresh_token.revoked:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Refresh token revoked"
            )

        expires_at = db_refresh_token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Refresh token expired"
            )

        db_refresh_token.revoked = True
        database_session.add(db_refresh_token)

        new_access_token = encode_admin_token(admin.uuid)

        new_jti = str(uuid4())
        new_refresh_token = encode_refresh_token(
            {"admin_uuid": str(admin.uuid), "admin": True}, new_jti,
            expiry_seconds=settings.admin_refresh_token_ttl_seconds,
        )

        new_db_token = AdminRefreshToken(
            admin_uuid=admin.uuid,
            refresh_token_jti=new_jti,
            created_at=now(),
            expires_at=now() + timedelta(seconds=settings.admin_refresh_token_ttl_seconds),
            revoked=False,
        )
        database_session.add(new_db_token)
        database_session.commit()

        response = JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Token refreshed successfully"},
        )
        response.set_cookie(
            **settings.admin_access_token_config(new_access_token, settings.admin_access_token_ttl_seconds)
        )
        response.set_cookie(
            **settings.admin_refresh_token_config(new_refresh_token, settings.admin_refresh_token_ttl_seconds)
        )
        return response

    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from e


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


def _payment_summary(alum_uuid: UUID, database_session: DBSession) -> PaymentSummary:
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
        return PaymentSummary()

    return PaymentSummary(
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
    alums = database_session.scalars(select(Alum)).all()
    entries = []
    for alum in alums:
        if alum.reg_code is None:
            continue
        _referrals, dates = referrals_for(database_session, alum.uuid)
        entries.append(
            ReferralLeaderboardEntry(
                alum_uuid=alum.uuid,
                full_name=alum.full_name,
                referral_code=alum.reg_code,
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
    if not alum or alum.reg_code is None:
        raise HTTPException(status_code=404, detail="Alum not found")
    referrals, dates = referrals_for(database_session, alum_uuid)
    return ReferralDrillDown(
        alum_uuid=alum.uuid,
        full_name=alum.full_name,
        referral_code=alum.reg_code,
        referral_count=len(dates),
        earliest_qualifying_referral=min(dates) if dates else None,
        referrals=referrals,
    )


def _full_information(alum: Alum, database_session: DBSession) -> AlumInformation:
    """Admin-side projection: includes status and profile even when incomplete."""
    work_profile = (
        database_session.get(WorkProfile, alum.work_profile_uuid)
        if alum.work_profile_uuid
        else None
    )

    profile_information = AlumniProfileInformation(
        uuid=alum.uuid,
        reg_code=alum.reg_code,
        student_id=alum.student_id,
        batch_year=alum.batch_year,
        tee_shirt_size=alum.tee_shirt_size,
        gender=alum.gender,
        academic_group=alum.academic_group,
        registered_at=alum.registered_at,
        profile_picture=alum.profile_picture,
        work_profile=(
            WorkProfileInformation.model_validate(
                work_profile, from_attributes=True
            )
            if work_profile
            else None
        ),
        address=AddressInformation.model_validate(alum, from_attributes=True),
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
