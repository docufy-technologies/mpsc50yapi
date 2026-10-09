from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- Auth ----------
class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=150)
    student_id: str | None = None
    batch_year: int = Field(ge=1950, le=2030)
    department: str
    phone: str
    current_org: str | None = None
    designation: str | None = None
    city: str | None = None
    country: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    full_name: str
    student_id: str | None
    batch_year: int
    department: str
    phone: str
    current_org: str | None
    designation: str | None
    city: str | None
    country: str | None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    is_admin: bool
    profile: ProfileOut | None


# ---------- Events ----------
class EventIn(BaseModel):
    title: str
    description: str | None = None
    venue: str
    event_date: date
    registration_deadline: datetime
    capacity: int | None = Field(default=None, ge=1)
    fee_per_person: Decimal = Field(default=Decimal("0"), ge=0)
    is_open: bool = True


class EventOut(EventIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ---------- Registrations ----------
class GuestIn(BaseModel):
    full_name: str
    relation: str | None = None
    age_group: Literal["adult", "child"] = "adult"
    dietary_preference: str | None = None


class GuestOut(GuestIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class RegistrationIn(BaseModel):
    event_id: int
    tshirt_size: Literal["S", "M", "L", "XL", "XXL"] | None = None
    dietary_preference: str | None = None
    needs_accommodation: bool = False
    special_requests: str | None = None
    guests: list[GuestIn] = Field(default_factory=list, max_length=10)


class RegistrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_id: int
    reg_code: str
    status: str
    tshirt_size: str | None
    dietary_preference: str | None
    needs_accommodation: bool
    special_requests: str | None
    total_amount: Decimal
    payment_status: str
    payment_method: str | None
    transaction_ref: str | None
    registered_at: datetime
    checked_in_at: datetime | None
    guests: list[GuestOut]


class PaymentUpdate(BaseModel):
    """Admin marks a payment after verifying it."""
    payment_status: Literal["unpaid", "paid", "refunded"]
    payment_method: str | None = None
    transaction_ref: str | None = None
