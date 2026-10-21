from datetime import UTC
from typing import Any
from uuid import UUID

import jwt
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from app.database import DBSession
from app.helper import now
from app.models import (
    Acquaintance,
    Alum,
    RefreshToken,
    WorkProfile,
)
from app.schemas.alumni import (
    AcquaintanceInformation,
    AddressInformation,
    AlumInformation,
    AlumniProfileInformation,
    AlumRegister,
    UpdateProfileRequest,
    WorkProfileInformation,
)
from app.schemas.auth import AlumLogin, PasswordUpdate
from app.services.auth import (
    CurrentAlum,
    encode_alum_access_token,
    encode_alum_refresh_token,
    get_refresh_token_record,
    hash_password,
    verify_password,
)
from app.services.deadlines import ensure_open
from app.services.payment import payment_summary
from app.services.token import decode_token
from app.settings import settings

router = APIRouter(prefix="/auth", tags=["Authentication Routes"])


def _alum_information(alum: Alum, database_session: Session) -> AlumInformation:

    profile_information = None

    work_profile_information = None
    if alum.work_profile_uuid:
        work_profile = database_session.get(WorkProfile, alum.work_profile_uuid)
        if work_profile:
            work_profile_information = WorkProfileInformation.model_validate(
                work_profile, from_attributes=True
            )

    address_information = AddressInformation.model_validate(alum, from_attributes=True)

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
        work_profile=work_profile_information,
        address=address_information,
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
        payment=payment_summary(alum.uuid, database_session),
        acquaintances=[
            AcquaintanceInformation.model_validate(acquaintance, from_attributes=True)
            for acquaintance in acquaintances
        ],
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=AlumInformation,
    summary=(
        "Register a new alum and issue an access token. "
        "The response carries the same body as /auth/login so the client can go "
        "straight to POST /payments/initiate."
    ),
)
def register(data: AlumRegister, database_session: DBSession):
    ensure_open("registration")
    email = data.email.lower()
    if database_session.scalar(select(Alum).where(Alum.email == email)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already registered",
        )

    referrer = None
    if data.referrer_reg_code:
        referrer = database_session.scalar(
            select(Alum).where(Alum.reg_code == data.referrer_reg_code)
        )
        if not referrer:
            pass  # reasoning[reakibulhasanratul]: Typo mistakes happen. Let them allow registration without a referrer!

    work_profile: WorkProfile | None = None
    if data.work_profile and not data.work_profile.is_empty():
        work_profile = WorkProfile(**data.work_profile.model_dump())
        database_session.add(work_profile)
        database_session.flush()

    alum = Alum(
        full_name=data.full_name,
        email=email,
        phone_number=data.phone_number,
        password_hash=hash_password(data.password),
        status="pending",
        student_id=data.student_id,
        batch_year=data.batch_year,
        tee_shirt_size=data.tee_shirt_size,
        gender=data.gender,
        academic_group=data.academic_group,
        referred_by_alum_uuid=referrer.uuid if referrer else None,
        work_profile_uuid=work_profile.uuid if work_profile else None,
        **data.address.model_dump(),
    )
    database_session.add(alum)
    database_session.flush()

    for acquaintance in data.acquaintances:
        database_session.add(
            Acquaintance(alum_uuid=alum.uuid, **acquaintance.model_dump())
        )

    database_session.commit()
    database_session.refresh(alum)

    # Registration sets the cookie too: the flow is register -> pay -> approval,
    # so a pending alum must be able to reach /payments/initiate without logging in.
    access_token = encode_alum_access_token(alum)
    refresh_token, refresh_token_record = encode_alum_refresh_token(alum)
    database_session.add(refresh_token_record)
    database_session.commit()
    response_data = _alum_information(alum, database_session)
    response = JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_data.model_dump(mode="json"),
    )
    response.set_cookie(**settings.access_token_cookie_param(access_token, "alum"))
    response.set_cookie(**settings.refresh_token_cookie_param(refresh_token, "alum"))
    return response


@router.post(
    "/login",
    response_model=AlumInformation,
    summary="Authenticate an alum and issue an access token",
)
def login(cred: AlumLogin, database_session: DBSession):
    alum = database_session.scalar(select(Alum).where(Alum.email == cred.email.lower()))
    if not alum or not verify_password(cred.password, alum.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    # Only `cancelled` is refused; a `pending` alum has paid but is unapproved.
    if alum.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )

    access_token = encode_alum_access_token(alum)
    refresh_token, refresh_token_record = encode_alum_refresh_token(alum)
    database_session.add(refresh_token_record)
    database_session.commit()
    response_data = _alum_information(alum, database_session)
    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_data.model_dump(mode="json"),
    )
    response.set_cookie(**settings.access_token_cookie_param(access_token, "alum"))
    response.set_cookie(**settings.refresh_token_cookie_param(refresh_token, "alum"))
    return response


@router.post("/logout", summary="Log out the current alum")
def logout(request: Request, database_session: DBSession):
    detail = "Logged out successfully"
    try:
        record = get_refresh_token_record(request, database_session, "alum")
        record.revoked = True
        database_session.add(record)
        database_session.commit()
    except HTTPException as e:
        detail = e.detail

    response = JSONResponse(status_code=status.HTTP_200_OK, content={"message": detail})
    response.delete_cookie(**settings.access_token_cookie_deletion_param("alum"))
    response.delete_cookie(**settings.refresh_token_cookie_deletion_param("alum"))
    return response


@router.post(
    "/refresh-token",
    summary="Refresh the current alum's access token",
)
def refresh_access_token(request: Request, database_session: DBSession):
    record = get_refresh_token_record(request, database_session, "alum")

    if record.revoked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Refresh token revoked"
        )

    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < now():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Refresh token expired"
        )

    alum = database_session.get(Alum, record.entity_uuid)
    if not alum or alum.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
        )

    # Revoke the old record and issue a fresh access + refresh pair.
    record.revoked = True
    database_session.add(record)

    new_access_token = encode_alum_access_token(alum)
    new_refresh_token, new_record = encode_alum_refresh_token(alum)
    database_session.add(new_record)
    database_session.commit()

    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Token refreshed successfully"},
    )
    response.set_cookie(**settings.access_token_cookie_param(new_access_token, "alum"))
    response.set_cookie(
        **settings.refresh_token_cookie_param(new_refresh_token, "alum")
    )
    return response


@router.get("/verify-token", summary="Verify the validity of an access token")
def verify_token(request: Request, database_session: DBSession) -> dict[str, Any]:
    access_token = request.cookies.get(settings.alum_access_token)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
        )
    try:
        payload = decode_token(access_token)
        uuid_str: str | None = payload.get("uuid")
        if not uuid_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        # A valid signature is not enough: the account must still exist and not
        # be cancelled, or a dead alum stays "validated".
        alum = database_session.scalar(
            select(Alum).where(Alum.uuid == UUID(uuid_str), Alum.status != "cancelled")
        )
        if not alum:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is not active",
            )

        return {"message": "Validated", "data": {"uuid": str(alum.uuid)}}
    except HTTPException:
        raise
    except (jwt.InvalidTokenError, ValueError, TypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token"
        ) from e


@router.get(
    "/me",
    summary="Get the current alum's information",
    response_model=AlumInformation,
)
def get_alum_information(alum: CurrentAlum, database_session: DBSession):
    return _alum_information(alum, database_session)


@router.put(
    "/update-profile",
    summary="Update the current alum's profile",
    response_model=AlumInformation,
)
def update_alum_profile(
    data: UpdateProfileRequest,
    alum: CurrentAlum,
    database_session: DBSession,
):
    if data.full_name is not None:
        alum.full_name = data.full_name
    if data.phone_number is not None:
        alum.phone_number = data.phone_number

    database_session.add(alum)
    database_session.commit()
    database_session.refresh(alum)

    return _alum_information(alum, database_session)


@router.put("/update-password", summary="Update the current alum's password")
def update_alum_password(
    cred: PasswordUpdate,
    alum: CurrentAlum,
    database_session: DBSession,
):
    if not verify_password(cred.current_password, alum.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid current password",
        )
    alum.password_hash = hash_password(cred.new_password)

    tokens = database_session.scalars(
        select(RefreshToken).where(
            RefreshToken.entity_uuid == alum.uuid, RefreshToken.revoked == False
        )
    ).all()
    for token in tokens:
        token.revoked = True
        database_session.add(token)

    database_session.commit()
    return {"message": "Password updated successfully"}
