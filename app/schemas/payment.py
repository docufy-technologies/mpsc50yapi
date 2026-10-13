from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.types import PaymentStatus


class PaymentInformation(BaseModel):
    uuid: UUID
    amount: int
    transaction_reference: str
    status: PaymentStatus
    paid_at: datetime

    model_config = {"from_attributes": True}


class PaymentSessionResponse(BaseModel):
    transaction_reference: str
    gateway_url: str
    session_key: str


class AdminPaymentSummary(BaseModel):
    """Latest payment for one alumna. Defaults to unpaid."""

    has_paid: bool = False
    latest_status: PaymentStatus = "unpaid"
    amount: int | None = None
    transaction_reference: str | None = None
    paid_at: datetime | None = None

    model_config = {"from_attributes": True}


class PaymentCallback(BaseModel):
    """Recorded outcome of a validated transaction. Kept for the admin/audit
    view and for tests; the browser callback itself responds with a redirect."""

    status: PaymentStatus
    transaction_reference: str
    reason: str = ""
    gateway_validation: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}