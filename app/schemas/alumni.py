from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.payment import AdminPaymentSummary
from app.types import AcademicGroup, AgeGroup, TeeShirtSize


class WorkProfileCreate(BaseModel):
    organization_name: str
    designation: str
    department_or_division: str


class WorkProfileInformation(BaseModel):
    uuid: UUID
    organization_name: str
    designation: str
    department_or_division: str


class AddressCreate(BaseModel):
    street_address: str
    city: str
    state_or_province: str
    postal_code: str
    country: str


class AddressInformation(BaseModel):
    uuid: UUID
    street_address: str
    city: str
    state_or_province: str
    postal_code: str
    country: str


class AcquaintanceCreate(BaseModel):
    full_name: str
    relation: str
    age_group: AgeGroup


class AcquaintanceInformation(BaseModel):
    uuid: UUID
    full_name: str
    relation: str
    age_group: AgeGroup


class AlumniProfileInformation(BaseModel):
    uuid: UUID
    reg_code: str
    student_id: str | None
    batch_year: int
    tee_shirt_size: str
    academic_group: str | None = None
    registered_at: datetime
    work_profile: WorkProfileInformation | None = None
    address: AddressInformation | None = None


class AlumnaInformation(BaseModel):
    uuid: UUID
    full_name: str
    email: EmailStr
    phone_number: str
    status: str
    created_at: datetime
    profile: AlumniProfileInformation | None = None
    # Only populated by the admin projection; alumna routes leave it empty.
    payment: AdminPaymentSummary = Field(default_factory=AdminPaymentSummary)
    acquaintances: list[AcquaintanceInformation] = Field(default_factory=list)


class AlumnaRegister(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    phone_number: str = Field(max_length=16)
    password: str = Field(min_length=8, max_length=128)

    batch_year: int = Field(ge=1976, le=datetime.now(tz=UTC).year)
    tee_shirt_size: TeeShirtSize
    academic_group: AcademicGroup | None = None
    student_id: str | None = None
    reg_code: str | None = None
    referrer: str | None = Field(default=None, min_length=1, max_length=64)

    work_profile: WorkProfileCreate | None = None
    address: AddressCreate | None = None
    acquaintances: list[AcquaintanceCreate] = Field(default_factory=list)


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    # Must match the Alumna.phone_number column width, as AlumnaRegister does.
    phone_number: str | None = Field(default=None, max_length=16)
