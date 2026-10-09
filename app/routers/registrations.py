from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_admin, get_current_user
from ..models import Event, Guest, Registration, User
from ..schemas import PaymentUpdate, RegistrationIn, RegistrationOut

router = APIRouter(tags=["Registrations"])


def headcount(db: Session, event_id: int) -> int:
    """People holding a place (alumni + their guests). Waitlisted and cancelled do not count."""
    regs = db.scalars(
        select(Registration).where(
            Registration.event_id == event_id,
            Registration.status.in_(["pending", "confirmed"]),
        )
    ).all()
    return sum(1 + len(r.guests) for r in regs)


@router.post("/registrations", response_model=RegistrationOut, status_code=status.HTTP_201_CREATED)
def register(data: RegistrationIn, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    event = db.get(Event, data.event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")

    deadline = event.registration_deadline
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if not event.is_open or datetime.now(timezone.utc) > deadline:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Registration for this event is closed")

    existing = db.scalar(
        select(Registration).where(
            Registration.user_id == user.id, Registration.event_id == event.id
        )
    )
    if existing and existing.status != "cancelled":
        raise HTTPException(status.HTTP_409_CONFLICT, "You are already registered for this event")

    people = 1 + len(data.guests)
    full = event.capacity is not None and headcount(db, event.id) + people > event.capacity

    if existing:  # re-registering after a cancellation: reuse the row
        for guest in list(existing.guests):
            db.delete(guest)
        reg = existing
        reg.payment_status = "unpaid"
    else:
        reg = Registration(user_id=user.id, event_id=event.id)
        db.add(reg)

    reg.status = "waitlisted" if full else "pending"
    reg.tshirt_size = data.tshirt_size
    reg.dietary_preference = data.dietary_preference
    reg.needs_accommodation = data.needs_accommodation
    reg.special_requests = data.special_requests
    reg.total_amount = event.fee_per_person * people
    reg.guests = [Guest(**g.model_dump()) for g in data.guests]
    db.commit()
    db.refresh(reg)
    return reg


@router.get("/registrations/me", response_model=list[RegistrationOut])
def my_registrations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Registration).where(Registration.user_id == user.id)).all()


@router.post("/registrations/{reg_id}/cancel", response_model=RegistrationOut)
def cancel_registration(reg_id: int, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    reg = db.get(Registration, reg_id)
    if not reg or reg.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registration not found")
    reg.status = "cancelled"
    db.commit()
    db.refresh(reg)
    return reg


# ---------- Admin ----------
@router.get("/admin/registrations", response_model=list[RegistrationOut],
            dependencies=[Depends(get_current_admin)])
def all_registrations(event_id: int | None = None, db: Session = Depends(get_db)):
    query = select(Registration).order_by(Registration.registered_at)
    if event_id:
        query = query.where(Registration.event_id == event_id)
    return db.scalars(query).all()


@router.patch("/admin/registrations/{reg_id}/payment", response_model=RegistrationOut,
              dependencies=[Depends(get_current_admin)])
def update_payment(reg_id: int, data: PaymentUpdate, db: Session = Depends(get_db)):
    reg = db.get(Registration, reg_id)
    if not reg:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registration not found")
    reg.payment_status = data.payment_status
    reg.payment_method = data.payment_method
    reg.transaction_ref = data.transaction_ref
    if data.payment_status == "paid" and reg.status == "pending":
        reg.status = "confirmed"  # paid pending registrations become confirmed
    db.commit()
    db.refresh(reg)
    return reg
