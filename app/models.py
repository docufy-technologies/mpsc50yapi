from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel

from app.helper import now


class Payment(SQLModel, table=True):
    __tablename__ = "payments"  # type: ignore[assignment]

    uuid: UUID = Field(default_factory=uuid4, primary_key=True)
    amount: int = Field(gt=0)
    transaction_reference: str
    status: str
    paid_at: datetime = Field(default_factory=now, index=True)


class Alumna(SQLModel, table=True):
    __tablename__ = "alumni"  # type: ignore[assignment]

    uuid: UUID = Field(default_factory=uuid4, primary_key=True)
    full_name: str
    email: str = Field(unique=True, index=True)
    phone_number: str = Field(max_length=16, index=True)
    password_hash: str
    created_at: datetime = Field(default_factory=now, index=True)
    status: str


class AlumniPayment(SQLModel, table=True):
    __tablename__ = "alumni_payments"  # type: ignore[assignment]

    uuid: UUID = Field(default_factory=uuid4, primary_key=True)
    alumna_uuid: UUID | None = Field(
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


class Address(SQLModel, table=True):
    __tablename__ = "addresses"  # type: ignore[assignment]

    uuid: UUID = Field(default_factory=uuid4, primary_key=True)
    street_address: str
    city: str
    state_or_province: str
    postal_code: str
    country: str


class AlumniProfile(SQLModel, table=True):
    __tablename__ = "alumni_profiles"  # type: ignore[assignment]

    uuid: UUID = Field(default_factory=uuid4, primary_key=True)
    alumna_uuid: UUID | None = Field(
        default=None, foreign_key="alumni.uuid", unique=True, ondelete="CASCADE"
    )
    reg_code: str = Field(unique=True)
    student_id: str | None = Field(default=None)
    batch_year: int = Field(ge=1976, le=now().year)
    tee_shirt_size: str

    # foreign keys
    work_profile_uuid: UUID | None = Field(
        default=None, foreign_key="work_profiles.uuid", ondelete="SET NULL"
    )
    address_uuid: UUID | None = Field(
        default=None, foreign_key="addresses.uuid", ondelete="SET NULL"
    )

    registered_at: datetime = Field(default_factory=now, index=True)


class Acquaintance(SQLModel, table=True):
    __tablename__ = "acquaintances"  # type: ignore[assignment]

    uuid: UUID = Field(default_factory=uuid4, primary_key=True)
    alumna_uuid: UUID | None = Field(
        default=None, foreign_key="alumni.uuid", ondelete="CASCADE"
    )
    full_name: str
    relation: str
    age_group: str
