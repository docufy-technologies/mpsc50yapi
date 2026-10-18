from typing import cast
from uuid import UUID

from sqlmodel import Session, case, col, select

from app.models import AlumniPayment, Payment
from app.schemas.payment import PaymentSummary
from app.types import PaymentStatus


def payment_summary(alum_uuid: UUID, database_session: Session) -> PaymentSummary:
    """Return the current alum's settled payment state.

    Completed payments take precedence over failed or cancelled attempts so a
    later retry cannot hide an earlier successful payment.
    """
    payment = database_session.scalar(
        select(Payment)
        .join(AlumniPayment, col(AlumniPayment.payment_uuid) == col(Payment.uuid))
        .where(col(AlumniPayment.alum_uuid) == alum_uuid)
        .order_by(
            case((col(Payment.status) == "completed", 0), else_=1),
            col(Payment.paid_at).desc(),
        )
        .limit(1)
    )

    if not payment:
        return PaymentSummary()

    return PaymentSummary(
        has_paid=payment.status == "completed",
        latest_status=cast(PaymentStatus, payment.status),
        amount=payment.amount,
        transaction_reference=payment.transaction_reference,
        paid_at=payment.paid_at,
    )
