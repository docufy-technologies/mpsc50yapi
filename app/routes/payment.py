from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel import col, select

from app.dependencies import CurrentAlumna, DBSession
from app.helper import now
from app.models import AlumniPayment, Payment
from app.schemas.payment import PaymentInformation, PaymentSessionResponse
from app.services.sslcommerz import (
    ValidationOutcome,
    create_payment_session,
    reconcile_validation,
    validate_transaction,
)
from app.settings import settings

router = APIRouter(prefix="/payments", tags=["Payment Routes"])

# States that are not settled. Used by the admin listing.
OPEN_STATUSES = ("unpaid", "failed")


def _own_payment(
    database_session: DBSession, alumna: CurrentAlumna, payment_uuid: UUID
) -> Payment:
    link = database_session.scalar(
        select(AlumniPayment).where(
            AlumniPayment.payment_uuid == payment_uuid,
            AlumniPayment.alumna_uuid == alumna.uuid,
        )
    )
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found"
        )

    payment = database_session.get(Payment, payment_uuid)
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found"
        )

    return payment


def _to_information(payment: Payment) -> PaymentInformation:
    return PaymentInformation.model_validate(payment)


def _parse_gateway_timestamp(validation: dict[str, Any]) -> datetime | None:
    """SSLCommerz sends naive local timestamps; the column is timezone-aware."""
    raw = validation.get("validation_date") or validation.get("store_date")
    if not raw:
        return None

    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        return None

    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _settle_payment(
    database_session: DBSession,
    payment: Payment,
    outcome: ValidationOutcome,
) -> Payment:
    """Apply a reconciliation outcome to the payment row."""
    payment.status = "completed" if outcome.is_valid else "failed"

    if outcome.is_valid:
        paid_at = _parse_gateway_timestamp(outcome.raw)
        if paid_at:
            payment.paid_at = paid_at

    database_session.add(payment)
    database_session.commit()
    database_session.refresh(payment)

    return payment


async def _reconcile(
    database_session: DBSession, transaction_reference: str
) -> tuple[Payment, ValidationOutcome]:
    """Verify a payment against the gateway. Shared by callback and IPN."""
    payment = database_session.scalar(
        select(Payment).where(Payment.transaction_reference == transaction_reference)
    )
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found"
        )

    validation = await validate_transaction(transaction_reference)
    outcome = reconcile_validation(
        validation,
        expected_reference=transaction_reference,
        expected_amount=payment.amount,
        expected_currency="BDT",
    )

    return payment, outcome


@router.post(
    "/initiate",
    response_model=PaymentSessionResponse,
    summary="Create an SSLCommerz session and redirect the alumna to the gateway",
)
async def initiate_payment(
    alumna: CurrentAlumna,
    database_session: DBSession,
) -> PaymentSessionResponse:
    existing_payments = database_session.scalars(
        select(Payment)
        .join(AlumniPayment, col(AlumniPayment.payment_uuid) == col(Payment.uuid))
        .where(col(AlumniPayment.alumna_uuid) == alumna.uuid)
    ).all()

    if any(payment.status == "completed" for payment in existing_payments):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment for this alumna is already completed",
        )

    # Only `unpaid` is reusable. A `failed` payment may still have gateway
    # records, so a retry gets a fresh reference.
    reusable = next(
        (payment for payment in existing_payments if payment.status == "unpaid"),
        None,
    )

    if reusable:
        payment = reusable
        transaction_reference = payment.transaction_reference
    else:
        transaction_reference = f"MPSC50-{uuid4().hex[:16].upper()}"
        payment = Payment(
            amount=settings.event_fee_bdt,
            transaction_reference=transaction_reference,
            status="unpaid",
            paid_at=now(),
        )
        database_session.add(payment)
        database_session.flush()

        database_session.add(
            AlumniPayment(alumna_uuid=alumna.uuid, payment_uuid=payment.uuid)
        )
        database_session.commit()

    session = await create_payment_session(
        transaction_reference=transaction_reference,
        amount=payment.amount,
        product_name="MPSC 50 Years Golden Jubilee Participation",
        alumna_email=alumna.email,
        alumna_name=alumna.full_name,
        # The browser lands on the API so it is validated before success is shown.
        success_url=f"{settings.api_url}/payments/callback",
        cancel_url=f"{settings.frontend_url}/payment/cancelled",
        ipn_url=f"{settings.api_url}/payments/ipn",
    )

    return PaymentSessionResponse(
        transaction_reference=transaction_reference,
        gateway_url=session.gateway_url,
        session_key=session.session_key,
    )


@router.get(
    "/me",
    response_model=list[PaymentInformation],
    summary="List the current alumna's payments",
)
def list_my_payments(
    alumna: CurrentAlumna, database_session: DBSession
) -> list[PaymentInformation]:
    payments = database_session.scalars(
        select(Payment)
        .join(AlumniPayment, col(AlumniPayment.payment_uuid) == col(Payment.uuid))
        .where(col(AlumniPayment.alumna_uuid) == alumna.uuid)
        .order_by(col(Payment.paid_at).desc())
    ).all()

    return [_to_information(payment) for payment in payments]


@router.get(
    "/{payment_uuid}",
    response_model=PaymentInformation,
    summary="Get one of the current alumna's payments",
)
def get_my_payment(
    payment_uuid: UUID,
    alumna: CurrentAlumna,
    database_session: DBSession,
) -> PaymentInformation:
    return _to_information(_own_payment(database_session, alumna, payment_uuid))


@router.post(
    "/callback",
    summary="SSLCommerz browser redirect; validates then forwards to the frontend",
)
async def payment_callback(
    request: Request,
    database_session: DBSession,
) -> RedirectResponse:
    """The browser lands here after checkout. We validate server-side and then
    bounce to the frontend, so a hit on this URL without paying cannot settle
    anything."""
    form = await request.form()
    transaction_reference = str(form.get("tran_id") or "")
    frontend = settings.frontend_url

    if not transaction_reference:
        return RedirectResponse(
            f"{frontend}/payment/cancelled?reason=missing_reference",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        payment, outcome = await _reconcile(database_session, transaction_reference)
    except HTTPException as e:
        # 404 from an unknown reference, 503 from unconfigured gateway.
        return RedirectResponse(
            f"{frontend}/payment/cancelled?reason={e.status_code}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    _settle_payment(database_session, payment, outcome)

    if outcome.is_valid:
        return RedirectResponse(
            f"{frontend}/payment/success?tran_id={transaction_reference}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(
        f"{frontend}/payment/cancelled?reason={quote(outcome.reason)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/ipn", summary="SSLCommerz server-to-server payment notification")
async def payment_ipn(
    request: Request,
    database_session: DBSession,
) -> dict[str, Any]:
    """Instant Payment Notification.

    This is the reliable signal: it arrives server-to-server even if the alumna
    closes the browser before the redirect. SSLCommerz expects a 200 with no
    body, so errors are reported in the payload rather than as status codes.
    """
    form = await request.form()
    transaction_reference = str(form.get("tran_id") or "")
    status_from_gateway = str(form.get("status") or "")

    if not transaction_reference:
        return {"received": False, "reason": "missing transaction reference"}

    payment = database_session.scalar(
        select(Payment).where(Payment.transaction_reference == transaction_reference)
    )
    if not payment:
        return {"received": False, "reason": "unknown transaction reference"}

    if payment.status == "completed":
        return {"received": True, "status": "completed", "note": "already settled"}

    if status_from_gateway.upper() != "VALID":
        # Don't overwrite an in-flight state on a non-VALID notification; the
        # browser callback or a later IPN is authoritative.
        return {
            "received": True,
            "status": payment.status,
            "note": f"gateway reported {status_from_gateway or 'no status'}",
        }

    try:
        payment, outcome = await _reconcile(database_session, transaction_reference)
    except HTTPException as e:
        return {"received": True, "status": payment.status, "error": e.detail}

    _settle_payment(database_session, payment, outcome)

    return {
        "received": True,
        "status": payment.status,
        "reason": outcome.reason,
    }


@router.post(
    "/{payment_uuid}/confirm",
    response_model=PaymentInformation,
    summary="Manually mark a payment completed (offline/cash payments)",
)
def confirm_payment_manually(
    payment_uuid: UUID,
    alumna: CurrentAlumna,
    database_session: DBSession,
) -> PaymentInformation:
    return _to_information(
        _settle_payment(
            database_session,
            _own_payment(database_session, alumna, payment_uuid),
            ValidationOutcome(is_valid=True, reason="confirmed manually", raw={}),
        )
    )