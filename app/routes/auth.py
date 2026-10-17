from typing import Any
from uuid import UUID

import jwt

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from app.dependencies import CurrentAlum, DBSession
from app.models import (
    Acquaintance,
    Alum,
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
from datetime import timedelta, timezone
from uuid import uuid4

from app.helper import now
from app.models import RefreshToken
from app.services.auth import hash_password, verify_password
from app.services.token import (
    decode_token,
    encode_access_token,
    encode_refresh_token,
)
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
    access_token = encode_access_token({"uuid": str(alum.uuid)})

    refresh_jti = str(uuid4())
    refresh_token = encode_refresh_token({"uuid": str(alum.uuid)}, refresh_jti)
    database_session.add(
        RefreshToken(
            alum_uuid=alum.uuid,
            refresh_token_jti=refresh_jti,
            created_at=now(),
            expires_at=now() + timedelta(seconds=settings.alum_refresh_token_ttl_seconds),
            revoked=False,
        )
    )
    database_session.commit()

    response_data = _alum_information(alum, database_session)

    response = JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_data.model_dump(mode="json"),
    )
    response.set_cookie(
        **settings.access_token_config(access_token, settings.access_token_ttl_seconds)
    )
    response.set_cookie(
        **settings.refresh_token_config(refresh_token, settings.alum_refresh_token_ttl_seconds)
    )
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

    access_token = encode_access_token({"uuid": str(alum.uuid)})

    refresh_jti = str(uuid4())
    refresh_token = encode_refresh_token({"uuid": str(alum.uuid)}, refresh_jti)
    database_session.add(
        RefreshToken(
            alum_uuid=alum.uuid,
            refresh_token_jti=refresh_jti,
            created_at=now(),
            expires_at=now() + timedelta(seconds=settings.alum_refresh_token_ttl_seconds),
            revoked=False,
        )
    )
    database_session.commit()

    response_data = _alum_information(alum, database_session)

    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_data.model_dump(mode="json"),
    )
    response.set_cookie(
        **settings.access_token_config(access_token, settings.access_token_ttl_seconds)
    )
    response.set_cookie(
        **settings.refresh_token_config(refresh_token, settings.alum_refresh_token_ttl_seconds)
    )
    return response


@router.post("/logout", summary="Log out the current alum")
def logout(request: Request, database_session: DBSession):
    refresh_token = request.cookies.get(settings.refresh_token_name)
    if refresh_token:
        try:
            payload = decode_token(refresh_token, verify_exp=False)
            jti = payload.get("jti")
            if jti:
                record = database_session.scalar(
                    select(RefreshToken).where(RefreshToken.refresh_token_jti == jti)
                )
                if record and not record.revoked:
                    record.revoked = True
                    database_session.add(record)
                    database_session.commit()
        except Exception:
            pass

    response = JSONResponse(
        status_code=status.HTTP_200_OK, content={"message": "Logged out successfully"}
    )
    response.delete_cookie(**settings.delete_cookie_config(settings.access_token_name))
    response.delete_cookie(**settings.delete_cookie_config(settings.refresh_token_name))
    return response


@router.post(
    "/refresh-token",
    summary="Refresh the current alum's access token",
)
def refresh_access_token(request: Request, database_session: DBSession):
    refresh_token = request.cookies.get(settings.refresh_token_name)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token provided"
        )

    try:
        payload = decode_token(refresh_token)
        uuid_str: str | None = payload.get("uuid")
        jti: str | None = payload.get("jti")
        token_type: str | None = payload.get("type")

        if not uuid_str or not jti or token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token payload",
            )

        alum = database_session.scalar(
            select(Alum).where(Alum.uuid == UUID(uuid_str), Alum.status != "cancelled")
        )
        if not alum:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
            )

        db_refresh_token = database_session.scalar(
            select(RefreshToken).where(
                RefreshToken.alum_uuid == alum.uuid,
                RefreshToken.refresh_token_jti == jti,
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

        # Revoke old token
        db_refresh_token.revoked = True
        database_session.add(db_refresh_token)

        # Issue new access + refresh tokens
        new_access_token = encode_access_token({"uuid": uuid_str})

        new_jti = str(uuid4())
        new_refresh_token = encode_refresh_token({"uuid": uuid_str}, new_jti)

        new_db_token = RefreshToken(
            alum_uuid=alum.uuid,
            refresh_token_jti=new_jti,
            created_at=now(),
            expires_at=now() + timedelta(seconds=settings.alum_refresh_token_ttl_seconds),
            revoked=False,
        )
        database_session.add(new_db_token)
        database_session.commit()

        response = JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Token refreshed successfully"},
        )
        response.set_cookie(
            **settings.access_token_config(new_access_token, settings.access_token_ttl_seconds)
        )
        response.set_cookie(
            **settings.refresh_token_config(new_refresh_token, settings.alum_refresh_token_ttl_seconds)
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


@router.get("/verify-token", summary="Verify the validity of an access token")
def verify_token(request: Request, database_session: DBSession) -> dict[str, Any]:
    access_token = request.cookies.get(settings.access_token_name)
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
    except Exception as e:
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
            RefreshToken.alum_uuid == alum.uuid, RefreshToken.revoked == False
        )
    ).all()
    for token in tokens:
        token.revoked = True
        database_session.add(token)

    database_session.commit()
    return {"message": "Password updated successfully"}
