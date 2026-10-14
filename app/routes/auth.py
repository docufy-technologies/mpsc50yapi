from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from app.dependencies import CurrentAlum, DBSession
from app.models import (
    Acquaintance,
    Address,
    Alum,
    AlumniProfile,
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
from app.schemas.auth import AlumLogin, PasswordUpdate, Token
from app.services.auth import hash_password, verify_password
from app.services.token import (
    ACCESS_TOKEN_TTL_SECONDS,
    decode_token,
    encode_access_token,
    is_within_refresh_window,
)
from app.settings import settings

router = APIRouter(prefix="/auth", tags=["Authentication Routes"])


def _alum_information(alum: Alum, database_session: Session) -> AlumInformation:

    profile = database_session.scalar(
        select(AlumniProfile).where(AlumniProfile.alum_uuid == alum.uuid)
    )

    assert profile is not None
    # reasoning[rakibulhasanratul]: According to the current design,
    # Alum is the bare minimum login entity & AlumniProfile holds the
    # extended information about an Alum. So, it is obvious that we
    # shall find a profile each alum

    profile_information = None

    work_profile_information = None
    if profile.work_profile_uuid:
        work_profile = database_session.get(WorkProfile, profile.work_profile_uuid)
        if work_profile:
            work_profile_information = WorkProfileInformation.model_validate(
                work_profile, from_attributes=True
            )

    address_information = None
    if profile.address_uuid:
        address = database_session.get(Address, profile.address_uuid)
        if address:
            address_information = AddressInformation.model_validate(
                address, from_attributes=True
            )

    profile_information = AlumniProfileInformation(
        uuid=profile.uuid,
        reg_code=profile.reg_code,
        student_id=profile.student_id,
        batch_year=profile.batch_year,
        tee_shirt_size=profile.tee_shirt_size,
        academic_group=profile.academic_group,
        registered_at=profile.registered_at,
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
            select(AlumniProfile).where(
                AlumniProfile.reg_code == data.referrer_reg_code
            )
        )
        if not referrer:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Referrer registration code not found",
            )
        if not database_session.get(Alum, referrer.alum_uuid):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Referrer registration code is not linked to an alum",
            )

    alum = Alum(
        full_name=data.full_name,
        email=email,
        phone_number=data.phone_number,
        password_hash=hash_password(data.password),
        status="pending",
    )
    database_session.add(alum)
    database_session.flush()

    work_profile: WorkProfile | None = None
    if data.work_profile and not data.work_profile.is_empty():
        work_profile = WorkProfile(**data.work_profile.model_dump())
        database_session.add(work_profile)

    address: Address | None = None
    if data.address and not data.address.is_empty():
        address = Address(**data.address.model_dump())
        database_session.add(address)

    if work_profile or address:
        database_session.flush()

    profile = AlumniProfile(
        alum_uuid=alum.uuid,
        student_id=data.student_id,
        batch_year=data.batch_year,
        tee_shirt_size=data.tee_shirt_size,
        academic_group=data.academic_group,
        referred_by_alum_uuid=referrer.alum_uuid if referrer else None,
        work_profile_uuid=work_profile.uuid if work_profile else None,
        address_uuid=address.uuid if address else None,
    )
    database_session.add(profile)

    for acquaintance in data.acquaintances:
        database_session.add(
            Acquaintance(alum_uuid=alum.uuid, **acquaintance.model_dump())
        )

    database_session.commit()
    database_session.refresh(alum)

    # Registration sets the cookie too: the flow is register -> pay -> approval,
    # so a pending alum must be able to reach /payments/initiate without logging in.
    access_token = encode_access_token({"uuid": str(alum.uuid)})
    response_data = _alum_information(alum, database_session)

    response = JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_data.model_dump(mode="json"),
    )
    response.set_cookie(
        **settings.access_token_config(access_token, ACCESS_TOKEN_TTL_SECONDS)
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
    response_data = _alum_information(alum, database_session)

    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_data.model_dump(mode="json"),
    )
    response.set_cookie(
        **settings.access_token_config(access_token, ACCESS_TOKEN_TTL_SECONDS)
    )
    return response


@router.post("/logout", summary="Log out the current alum")
def logout():
    response = JSONResponse(
        status_code=status.HTTP_200_OK, content={"message": "Logged out successfully"}
    )
    response.delete_cookie(**settings.delete_cookie_config(settings.access_token_name))
    return response


@router.post(
    "/refresh-token",
    summary="Refresh the current alum's access token",
    response_model=Token,
)
def refresh_access_token(request: Request, database_session: DBSession):
    access_token = request.cookies.get(settings.access_token_name)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No access token provided"
        )

    try:
        payload = decode_token(access_token, verify_exp=False)
        uuid_str: str | None = payload.get("uuid")
        if not uuid_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
            )

        if not is_within_refresh_window(payload):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is expired beyond the refresh window",
            )

        alum = database_session.scalar(
            select(Alum).where(Alum.uuid == UUID(uuid_str), Alum.status != "cancelled")
        )
        if not alum:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
            )

        new_access_token = encode_access_token({"uuid": uuid_str})
        response = JSONResponse(
            status_code=status.HTTP_200_OK,
            content=Token(access_token=new_access_token).model_dump(),
        )
        response.set_cookie(
            **settings.access_token_config(new_access_token, ACCESS_TOKEN_TTL_SECONDS)
        )
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token"
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
    database_session.commit()
    return {"message": "Password updated successfully"}
