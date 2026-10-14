from datetime import datetime

from pydantic import BaseModel


class EventInformation(BaseModel):
    name: str
    subtitle: str
    established_year: int
    celebration_year: int
    registration_deadline: str
    event_date: str
    venue: str
    participation_fee_bdt: int


class PublicStatistics(BaseModel):
    confirmed_alumni: int
    total_registrations: int
    batch_years_covered: int


class PublicDeadline(BaseModel):
    key: str
    label: str
    deadline_at: datetime
    is_extended: bool
    is_open: bool
