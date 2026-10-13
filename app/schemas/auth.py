from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class AlumLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class AdminLogin(BaseModel):
    email: EmailStr
    password: str


class AdminInfo(BaseModel):
    uuid: UUID
    email: str
    is_active: bool
    created_at: datetime


class AdminSession(BaseModel):
    message: str = "Admin session established"
    expires_in: int
