from uuid import UUID

from pydantic import BaseModel


class AlumniProfilePictureResponse(BaseModel):
    alum_uuid: UUID
    filename: str
