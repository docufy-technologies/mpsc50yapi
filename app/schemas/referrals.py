from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ReferredAlumInformation(BaseModel):
    uuid: UUID
    full_name: str
    status: str


class MyReferralsInformation(BaseModel):
    referral_code: str
    referral_count: int
    referrals: list[ReferredAlumInformation]


class ReferralLeaderboardEntry(BaseModel):
    alum_uuid: UUID
    full_name: str
    referral_code: str
    referral_count: int
    earliest_qualifying_referral: datetime | None


class ReferralDrillDown(BaseModel):
    alum_uuid: UUID
    full_name: str
    referral_code: str
    referral_count: int
    earliest_qualifying_referral: datetime | None
    referrals: list[ReferredAlumInformation]
