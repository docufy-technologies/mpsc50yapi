from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Text
from sqlmodel import Field, Relationship, SQLModel

from app.helper import now
from app.settings import settings


class Alum(SQLModel, table=True):
    __tablename__ = "alumni"  # type: ignore[assignment]

    uuid: UUID = Field(default_factory=uuid4, primary_key=True)
    full_name: str
    email: str = Field(unique=True, index=True)
    phone_number: str = Field(max_length=16, index=True)
    password_hash: str
    created_at: datetime = Field(default_factory=now, index=True)
    status: str

    # Merged from the former AlumniProfile (1:1, mandatory).
    reg_code: str | None = Field(default=None, unique=True)
    student_id: str | None = Field(default=None)
    referred_by_alum_uuid: UUID | None = Field(
        default=None, foreign_key="alumni.uuid", ondelete="SET NULL", index=True
    )
    batch_year: int
    tee_shirt_size: str
    gender: str
    # Constrained to AcademicGroup in the schema, not at the column.
    academic_group: str | None = Field(default=None)
    # Address is mandatory for SSLCommerz
    street_address: str
    city: str
    state_or_province: str
    postal_code: str
    country: str

    profile_picture: str | None = Field(default=None)

    @property
    def pfp_path(self) -> str:
        return (
            str(settings.form_alumni_pfp_file_path(self.profile_picture))
            if self.profile_picture
            else ""
        )

    # foreign keys
    work_profile_uuid: UUID | None = Field(
        default=None, foreign_key="work_profiles.uuid", ondelete="SET NULL"
    )

    registered_at: datetime = Field(default_factory=now, index=True)


class Payment(SQLModel, table=True):
    __tablename__ = "payments"  # type: ignore[assignment]

    uuid: UUID = Field(default_factory=uuid4, primary_key=True)
    amount: int
    transaction_reference: str
    status: str
    paid_at: datetime = Field(default_factory=now, index=True)


class AlumniPayment(SQLModel, table=True):
    __tablename__ = "alumni_payments"  # type: ignore[assignment]

    uuid: UUID = Field(default_factory=uuid4, primary_key=True)
    alum_uuid: UUID | None = Field(
        default=None, foreign_key="alumni.uuid", ondelete="CASCADE"
    )
    payment_uuid: UUID | None = Field(
        default=None, foreign_key="payments.uuid", ondelete="CASCADE"
    )

    payment: Payment = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[AlumniPayment.payment_uuid]"}
    )


class WorkProfile(SQLModel, table=True):
    __tablename__ = "work_profiles"  # type: ignore[assignment]

    uuid: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_name: str
    designation: str
    department_or_division: str


class Acquaintance(SQLModel, table=True):
    __tablename__ = "acquaintances"  # type: ignore[assignment]

    uuid: UUID = Field(default_factory=uuid4, primary_key=True)
    alum_uuid: UUID | None = Field(
        default=None, foreign_key="alumni.uuid", ondelete="CASCADE"
    )
    full_name: str
    relation: str
    age_group: str


class SubcommitteeApplication(SQLModel, table=True):
    __tablename__ = "subcommittee_applications"  # type: ignore[assignment]

    uuid: UUID = Field(default_factory=uuid4, primary_key=True)
    alum_uuid: UUID = Field(foreign_key="alumni.uuid", ondelete="CASCADE", unique=True)
    first_choice: str
    second_choice: str | None = Field(default=None)
    motivation: str = Field(sa_type=Text)
    availability_notes: str | None = Field(default=None, max_length=500)
    status: str = Field(default="submitted")
    admin_note: str | None = Field(default=None, sa_type=Text)
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class SponsorOffer(SQLModel, table=True):
    __tablename__ = "sponsor_offers"  # type: ignore[assignment]

    uuid: UUID = Field(default_factory=uuid4, primary_key=True)
    alum_uuid: UUID = Field(foreign_key="alumni.uuid", ondelete="CASCADE", index=True)
    sponsor_type: str
    sponsor_name: str
    contact_person: str
    phone: str = Field(max_length=16)
    email: str
    proposed_amount_bdt: int | None = Field(default=None)
    in_kind_description: str | None = Field(default=None, sa_type=Text)
    message: str = Field(sa_type=Text)
    status: str = Field(default="submitted")
    admin_note: str | None = Field(default=None, sa_type=Text)
    created_at: datetime = Field(default_factory=now)


class OpenMicEntry(SQLModel, table=True):
    __tablename__ = "openmic_entries"  # type: ignore[assignment]

    uuid: UUID = Field(default_factory=uuid4, primary_key=True)
    alum_uuid: UUID = Field(foreign_key="alumni.uuid", ondelete="CASCADE", index=True)
    performance_type: str
    title_or_description: str = Field(sa_type=Text)
    duration_minutes: int
    needs_equipment_or_accompaniment: bool
    equipment_notes: str | None = Field(default=None, sa_type=Text)
    performance_link: str | None = Field(default=None, max_length=2048)
    status: str = Field(default="submitted")
    admin_note: str | None = Field(default=None, sa_type=Text)
    scheduled_slot: str | None = Field(default=None, max_length=200)
    created_at: datetime = Field(default_factory=now)


class StallApplication(SQLModel, table=True):
    __tablename__ = "stall_applications"  # type: ignore[assignment]

    uuid: UUID = Field(default_factory=uuid4, primary_key=True)
    alum_uuid: UUID = Field(foreign_key="alumni.uuid", ondelete="CASCADE", unique=True)
    stall_name: str = Field(max_length=200)
    category: str
    description: str = Field(sa_type=Text)
    products: list[str] = Field(sa_type=JSON)
    space_needs: str = Field(sa_type=Text)
    power_needs: str = Field(sa_type=Text)
    number_of_helpers: int
    contact_phone: str = Field(max_length=16)
    website_or_social_link: str | None = Field(default=None, max_length=2048)
    status: str = Field(default="applied")
    stall_fee_status: str = Field(default="pending")
    admin_note: str | None = Field(default=None, sa_type=Text)
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class Admin(SQLModel, table=True):
    __tablename__ = "admins"  # type: ignore[assignment]

    uuid: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=now, index=True)


class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_tokens"  # type: ignore[assignment]

    uuid: UUID = Field(default_factory=uuid4, primary_key=True)
    jti: str = Field(unique=True, index=True)
    entity_uuid: UUID = Field(index=True)
    created_at: datetime  # no default factory, should be inserted while object creation
    expires_at: datetime
    revoked: bool = Field(default=False)
