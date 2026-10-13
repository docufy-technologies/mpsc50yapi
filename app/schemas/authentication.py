from pydantic import BaseModel, EmailStr, Field


class AlumnaLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class AdminLogin(BaseModel):
    """One shared credential, not per-person: approvals are not attributable."""

    admin_secret: str = Field(min_length=1, max_length=512)


class AdminSession(BaseModel):
    message: str = "Admin session established"
    expires_in: int
