import io

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlmodel import select

from app.dependencies import CurrentAlum, DBSession
from app.models import AlumniProfile
from app.schemas.media import AlumniProfilePictureResponse
from app.services.media import (
    _process_img,
    delete_alumni_profile_picture,
    save_alumni_profile_picture,
    validate_image_upload,
)
from app.settings import settings

router = APIRouter(prefix=f"/{settings.media_dir}", tags=["Media Routes"])


@router.post(
    "/alumni/profile-picture",
    response_model=AlumniProfilePictureResponse,
    summary="Upload profile picture for currently logged in alum",
)
async def upload_profile_picture(
    alum: CurrentAlum,
    database_session: DBSession,
    file: UploadFile = File(...),
) -> AlumniProfilePictureResponse:
    profile = database_session.scalar(
        select(AlumniProfile).where(AlumniProfile.alum_uuid == alum.uuid)
    )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alumni profile not found",
        )

    content = await validate_image_upload(file)
    processed_buffer = _process_img(io.BytesIO(content))

    # Save new picture
    new_filename = save_alumni_profile_picture(processed_buffer)

    # Delete previous picture if exists
    old_picture = profile.profile_picture
    if old_picture:
        delete_alumni_profile_picture(old_picture)

    # Update database record
    profile.profile_picture = new_filename
    database_session.add(profile)
    database_session.commit()
    database_session.refresh(profile)

    return AlumniProfilePictureResponse(alum_uuid=alum.uuid, filename=new_filename)


@router.delete(
    "/alumni/profile-picture",
    summary="Delete profile picture for currently logged in alum",
    response_model=AlumniProfilePictureResponse,
)
async def delete_profile_picture(
    alum: CurrentAlum,
    database_session: DBSession,
) -> AlumniProfilePictureResponse:
    profile = database_session.scalar(
        select(AlumniProfile).where(AlumniProfile.alum_uuid == alum.uuid)
    )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alumni profile not found",
        )

    # Delete previous picture if exists
    old_picture = profile.profile_picture
    if old_picture:
        delete_alumni_profile_picture(old_picture)
        profile.profile_picture = None
        database_session.add(profile)
        database_session.commit()
        database_session.refresh(profile)

    return AlumniProfilePictureResponse(alum_uuid=alum.uuid, filename="")
