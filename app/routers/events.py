from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_admin
from ..models import Event
from ..schemas import EventIn, EventOut

router = APIRouter(prefix="/events", tags=["Events"])


@router.get("/", response_model=list[EventOut])
def list_events(db: Session = Depends(get_db)):
    return db.scalars(select(Event).order_by(Event.event_date)).all()


@router.get("/{event_id}", response_model=EventOut)
def get_event(event_id: int, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    return event


@router.post("/", response_model=EventOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(get_current_admin)])
def create_event(data: EventIn, db: Session = Depends(get_db)):
    event = Event(**data.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
