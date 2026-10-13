from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from app.dependencies import CurrentAlumna, DBSession
from app.helper import generate_reg_code
from app.models import (
    Acquaintance,
    Address,
    Alumna,
    AlumniProfile,
    WorkProfile,
)
from app.schemas.alumni import (
    AcquaintanceInformation,
    AddressInformation,
    AlumnaInformation,
    AlumnaRegister,
    AlumniProfileInformation,
    UpdateProfileRequest,
    WorkProfileInformation,
)
from app.schemas.authentication import AlumnaLogin, PasswordUpdate, Token
from app.services.authentication import hash_password, verify_password
from app.services.token import (
    ACCESS_TOKEN_TTL_SECONDS,
    decode_token,
    encode_access_token,
    is_within_refresh_window,
)
from app.settings import settings

router = APIRouter(prefix="/auth", tags=["Authentication Routes"])


def _alumna_information(alumna: Alumna, database_session: Session) -> AlumnaInformation:
    profile = database_session.scalar(
        select(AlumniProfile).where(AlumniProfile.alumna_uuid == alumna.uuid)
    )

    profile_information = None
    if profile:
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
        acquaintances=[
            AcquaintanceInformation.model_validate(
                acquaintance, from_attributes=True
            )
            for acquaintance in acquaintances
        ],
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=AlumnaInformation,
    summary=(
        "Register a new alumna and issue an access token. "
        "The response carries the same body as /auth/login so the client can go "
        "straight to POST /payments/initiate."
    ),
)
def register(data: AlumnaRegister, database_session: DBSession):
    email = data.email.lower()
    if database_session.scalar(select(Alumna).where(Alumna.email == email)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already registered",
        )

    reg_code = data.reg_code or generate_reg_code()
    if database_session.scalar(
        select(AlumniProfile).where(AlumniProfile.reg_code == reg_code)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This registration code is already in use",
        )

    referrer = None
    if data.referrer:
        if data.referrer == reg_code:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="An alumna cannot refer herself",
            )
        referrer = database_session.scalar(
            select(AlumniProfile).where(AlumniProfile.reg_code == data.referrer)
        )
        if not referrer:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Referrer registration code not found",
            )
        if not referrer.alumna_uuid or not database_session.get(
            Alumna, referrer.alumna_uuid
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Referrer registration code is not linked to an alumna",
            )

    alumna = Alumna(
        full_name=data.full_name,
        email=email,
        phone_number=data.phone_number,
        password_hash=hash_password(data.password),
        status="pending",
    )
    database_session.add(alumna)
    database_session.flush()

    work_profile: WorkProfile | None = None
    if data.work_profile:
        work_profile = WorkProfile(**data.work_profile.model_dump())
        database_session.add(work_profile)

    address: Address | None = None
    if data.address:
        address = Address(**data.address.model_dump())
        database_session.add(address)

    if work_profile or address:
        database_session.flush()

    profile = AlumniProfile(
        alumna_uuid=alumna.uuid,
        reg_code=reg_code,
        student_id=data.student_id,
        batch_year=data.batch_year,
        tee_shirt_size=data.tee_shirt_size,
        academic_group=data.academic_group,
        referred_by_alumna_uuid=referrer.alumna_uuid if referrer else None,
        work_profile_uuid=work_profile.uuid if work_profile else None,
        address_uuid=address.uuid if address else None,
    )
    database_session.add(profile)

    for acquaintance in data.acquaintances:
        database_session.add(
            Acquaintance(alumna_uuid=alumna.uuid, **acquaintance.model_dump())
        )

    database_session.commit()
    database_session.refresh(alumna)

    # Registration sets the cookie too: the flow is register -> pay -> approval,
    # so a pending alumna must be able to reach /payments/initiate without logging in.
    access_token = encode_access_token({"uuid": str(alumna.uuid)})
    response_data = _alumna_information(alumna, database_session)

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
    response_model=AlumnaInformation,
    summary="Authenticate an alumna and issue an access token",
)
def login(cred: AlumnaLogin, database_session: DBSession):
    alumna = database_session.scalar(
        select(Alumna).where(Alumna.email == cred.email.lower())
    )
    if not alumna or not verify_password(cred.password, alumna.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    # Only `cancelled` is refused; a `pending` alumna has paid but is unapproved.
    if alumna.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )

    access_token = encode_access_token({"uuid": str(alumna.uuid)})
    response_data = _alumna_information(alumna, database_session)

    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_data.model_dump(mode="json"),
    )
    response.set_cookie(
        **settings.access_token_config(access_token, ACCESS_TOKEN_TTL_SECONDS)
    )
    return response


@router.post("/logout", summary="Log out the current alumna")
def logout():
    response = JSONResponse(
        status_code=status.HTTP_200_OK, content={"message": "Logged out successfully"}
    )
    response.delete_cookie(
        **settings.delete_cookie_config(settings.access_token_name)
    )
    return response


@router.post(
    "/refresh-token",
    summary="Refresh the current alumna's access token",
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

        alumna = database_session.scalar(
            select(Alumna).where(
                Alumna.uuid == UUID(uuid_str), Alumna.status != "cancelled"
            )
        )
        if not alumna:
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
        # be cancelled, or a dead alumna stays "validated".
        alumna = database_session.scalar(
            select(Alumna).where(
                Alumna.uuid == UUID(uuid_str), Alumna.status != "cancelled"
            )
        )
        if not alumna:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is not active",
            )

        return {"message": "Validated", "data": {"uuid": str(alumna.uuid)}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token"
        ) from e


@router.get(
    "/me",
    summary="Get the current alumna's information",
    response_model=AlumnaInformation,
)
def get_alumna_information(alumna: CurrentAlumna, database_session: DBSession):
    return _alumna_information(alumna, database_session)


@router.put(
    "/update-profile",
    summary="Update the current alumna's profile",
    response_model=AlumnaInformation,
)
def update_alumna_profile(
    data: UpdateProfileRequest,
    alumna: CurrentAlumna,
    database_session: DBSession,
):
    if data.full_name is not None:
        alumna.full_name = data.full_name
    if data.phone_number is not None:
        alumna.phone_number = data.phone_number

    database_session.add(alumna)
    database_session.commit()
    database_session.refresh(alumna)

    return _alumna_information(alumna, database_session)


@router.put(
    "/update-password", summary="Update the current alumna's password"
)
def update_alumna_password(
    cred: PasswordUpdate,
    alumna: CurrentAlumna,
    database_session: DBSession,
):
    if not verify_password(cred.current_password, alumna.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid current password",
        )
    alumna.password_hash = hash_password(cred.new_password)
    database_session.commit()
    return {"message": "Password updated successfully"}
