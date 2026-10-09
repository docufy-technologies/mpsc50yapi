import secrets
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_reg_code() -> str:
    return "ALM-" + secrets.token_hex(3).upper()


class User(Base):
    """Login account."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    profile: Mapped["AlumniProfile"] = relationship(back_populates="user", uselist=False)
    registrations: Mapped[list["Registration"]] = relationship(back_populates="user")


class AlumniProfile(Base):
    __tablename__ = "alumni_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150))
    student_id: Mapped[str | None] = mapped_column(String(50))
    batch_year: Mapped[int] = mapped_column(Integer)
    department: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(30))
    current_org: Mapped[str | None] = mapped_column(String(150))
    designation: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))

    user: Mapped[User] = relationship(back_populates="profile")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    venue: Mapped[str] = mapped_column(String(200))
    event_date: Mapped[date] = mapped_column(Date)
    registration_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    capacity: Mapped[int | None] = mapped_column(Integer)  # None = unlimited
    fee_per_person: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)

    registrations: Mapped[list["Registration"]] = relationship(back_populates="event")


class Registration(Base):
    __tablename__ = "registrations"
    __table_args__ = (UniqueConstraint("user_id", "event_id", name="one_registration_per_user_event"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    reg_code: Mapped[str] = mapped_column(String(20), unique=True, default=generate_reg_code)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending/confirmed/waitlisted/cancelled

    tshirt_size: Mapped[str | None] = mapped_column(String(3))
    dietary_preference: Mapped[str | None] = mapped_column(String(100))
    needs_accommodation: Mapped[bool] = mapped_column(Boolean, default=False)
    special_requests: Mapped[str | None] = mapped_column(Text)

    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    payment_status: Mapped[str] = mapped_column(String(10), default="unpaid")  # unpaid/paid/refunded
    payment_method: Mapped[str | None] = mapped_column(String(50))
    transaction_ref: Mapped[str | None] = mapped_column(String(100))

    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="registrations")
    event: Mapped[Event] = relationship(back_populates="registrations")
    guests: Mapped[list["Guest"]] = relationship(
        back_populates="registration", cascade="all, delete-orphan"
    )


class Guest(Base):
    __tablename__ = "guests"

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("registrations.id"))
    full_name: Mapped[str] = mapped_column(String(150))
    relation: Mapped[str | None] = mapped_column(String(50))
    age_group: Mapped[str] = mapped_column(String(5), default="adult")  # adult/child
    dietary_preference: Mapped[str | None] = mapped_column(String(100))

    registration: Mapped[Registration] = relationship(back_populates="guests")
