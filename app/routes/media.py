import io

from fastapi import APIRouter, File, UploadFile, status

from app.dependencies import CurrentAlum, DBSession
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
    f"/{settings.alumni_pfp_dir}",
    response_model=AlumniProfilePictureResponse,
    summary="Upload profile picture for currently logged in alum",
    status_code=status.HTTP_201_CREATED,
)
async def upload_profile_picture(
    alum: CurrentAlum,
    database_session: DBSession,
    file: UploadFile = File(...),
) -> AlumniProfilePictureResponse:
    content = await validate_image_upload(file)
    processed_buffer = _process_img(io.BytesIO(content))

    # Save new picture
    new_filename = save_alumni_profile_picture(processed_buffer)

    # Delete previous picture if exists
    old_picture = alum.profile_picture
    if old_picture:
        delete_alumni_profile_picture(old_picture)

    # Update database record
    alum.profile_picture = new_filename
    database_session.add(alum)
    database_session.commit()
    database_session.refresh(alum)

    return AlumniProfilePictureResponse(alum_uuid=alum.uuid, filename=new_filename)


@router.delete(
    f"/{settings.alumni_pfp_dir}",
    summary="Delete profile picture for currently logged in alum",
    response_model=AlumniProfilePictureResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def delete_profile_picture(
    alum: CurrentAlum,
    database_session: DBSession,
) -> AlumniProfilePictureResponse:
    old_picture = alum.profile_picture
    if old_picture:
        delete_alumni_profile_picture(old_picture)
        alum.profile_picture = None
        database_session.add(alum)
        database_session.commit()
        database_session.refresh(alum)

    return AlumniProfilePictureResponse(alum_uuid=alum.uuid, filename="")
