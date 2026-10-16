from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.schemas.payment import AdminPaymentSummary
from app.types import AcademicGroup, AgeGroup, Gender, TeeShirtSize


class WorkProfileCreate(BaseModel):
    organization_name: str | None = None
    designation: str | None = None
    department_or_division: str | None = None

    @model_validator(mode="after")
    def validate_all_or_none(self) -> "WorkProfileCreate":
        fields = [
            self.organization_name,
            self.designation,
            self.department_or_division,
        ]
        has_any = any(f is not None and f.strip() != "" for f in fields)
        has_all = all(f is not None and f.strip() != "" for f in fields)

        if has_any and not has_all:
            raise ValueError(
                "If any work profile field (organization name, designation, department) is provided, all 3 fields must be filled."
            )
        return self

    def is_empty(self) -> bool:
        return not any(
            f is not None and f.strip() != ""
            for f in [
                self.organization_name,
                self.designation,
                self.department_or_division,
            ]
        )


class WorkProfileInformation(BaseModel):
    uuid: UUID
    organization_name: str
    designation: str
    department_or_division: str


class AddressCreate(BaseModel):
    street_address: str = Field(min_length=1)
    city: str = Field(min_length=1)
    state_or_province: str = Field(min_length=1)
    postal_code: str = Field(min_length=1)
    country: str = Field(min_length=1)


class AddressInformation(BaseModel):
    street_address: str
    city: str
    state_or_province: str
    postal_code: str
    country: str

    model_config = {"from_attributes": True}


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
    reg_code: str | None = None
    student_id: str | None
    batch_year: int
    tee_shirt_size: str
    gender: str
    academic_group: str | None = None
    registered_at: datetime
    profile_picture: str | None = None
    work_profile: WorkProfileInformation | None = None
    address: AddressInformation


class AlumInformation(BaseModel):
    uuid: UUID
    full_name: str
    email: EmailStr
    phone_number: str
    status: str
    created_at: datetime
    profile: AlumniProfileInformation | None = None
    # Only populated by the admin projection; alum routes leave it empty.
    payment: AdminPaymentSummary = Field(default_factory=AdminPaymentSummary)
    acquaintances: list[AcquaintanceInformation] = Field(default_factory=list)


class AlumRegister(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    phone_number: str = Field(max_length=16)
    password: str = Field(min_length=8, max_length=128)

    batch_year: int = Field(ge=1976, le=datetime.now(tz=UTC).year)
    tee_shirt_size: TeeShirtSize
    gender: Gender
    academic_group: AcademicGroup | None = None
    student_id: str | None = None
    referrer_reg_code: str | None = Field(default=None, min_length=1, max_length=64)

    work_profile: WorkProfileCreate | None = None
    address: AddressCreate
    acquaintances: list[AcquaintanceCreate] = Field(default_factory=list)


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    # Must match the Alum.phone_number column width, as AlumRegister does.
    phone_number: str | None = Field(default=None, max_length=16)
