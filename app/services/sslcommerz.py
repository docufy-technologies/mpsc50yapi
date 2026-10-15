from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.settings import settings

SANDBOX_BASE_URL = "https://sandbox.sslcommerz.com"
LIVE_BASE_URL = "https://securepay.sslcommerz.com"


def _base_url() -> str:
    return SANDBOX_BASE_URL if settings.sslcommerz_is_sandbox else LIVE_BASE_URL


def _require_credentials() -> tuple[str, str]:
    if not settings.sslcommerz_store_id or not settings.sslcommerz_store_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment gateway is not configured",
        )
    return settings.sslcommerz_store_id, settings.sslcommerz_store_password


@dataclass
class PaymentSession:
    gateway_url: str
    session_key: str


async def create_payment_session(
    *,
    transaction_reference: str,
    amount: float,
    product_name: str,
    alum_email: str,
    alum_name: str,
    success_url: str,
    cancel_url: str,
    ipn_url: str,
) -> PaymentSession:
    store_id, store_password = _require_credentials()

    payload = {
        "store_id": store_id,
        "store_passwd": store_password,
        "total_amount": f"{amount:.2f}",
        "currency": "BDT",
        "tran_id": transaction_reference,
        "success_url": success_url,
        "fail_url": cancel_url,
        "cancel_url": cancel_url,
        "ipn_url": ipn_url,
        "product_name": product_name,
        "product_category": "Event",
        "product_profile": "general",
        "cus_name": alum_name,
        "cus_email": alum_email,
        "cus_add1": "N/A",
        "cus_city": "Dhaka",
        "cus_country": "Bangladesh",
        "cus_phone": "00000000000",
        "shipping_method": "NO",
        "ship_name": alum_name,
        "ship_add1": "N/A",
        "ship_city": "Dhaka",
        "ship_country": "Bangladesh",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{_base_url()}/gwprocess/v4/api.php", data=payload
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach the payment gateway",
        ) from e

    if data.get("status") != "SUCCESS":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=data.get("failedreason", "Payment session could not be created"),
        )

    return PaymentSession(
        gateway_url=data["GatewayPageURL"], session_key=data["sessionkey"]
    )


async def validate_transaction(transaction_reference: str) -> dict[str, Any]:

    store_id, store_password = _require_credentials()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{_base_url()}/validator/api/validationserverAPI.php",
                params={
                    "val_id": f"{store_id}-{transaction_reference}",
                    "store_id": store_id,
                    "store_passwd": store_password,
                    "format": "json",
                },
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not verify the transaction",
        ) from e


@dataclass
class ValidationOutcome:
    is_valid: bool
    reason: str
    raw: dict[str, Any]
    validated_amount: float | None = None
    validated_currency: str | None = None


def reconcile_validation(
    validation: dict[str, Any],
    *,
    expected_reference: str,
    expected_amount: int,
    expected_currency: str = "BDT",
) -> ValidationOutcome:

    raw = validation.get("status", "")
    gateway_status = str(raw).upper()

    if gateway_status != "VALID":
        return ValidationOutcome(
            is_valid=False,
            reason=f"gateway status is {gateway_status or 'missing'}",
            raw=validation,
        )

    returned_reference = str(validation.get("tran_id", ""))
    if returned_reference != expected_reference:
        return ValidationOutcome(
            is_valid=False,
            reason="transaction reference mismatch",
            raw=validation,
        )

    amount_raw = validation.get("amount")
    if amount_raw is None:
        return ValidationOutcome(
            is_valid=False, reason="gateway did not report an amount", raw=validation
        )

    try:
        validated_amount = float(amount_raw)
    except (TypeError, ValueError):
        return ValidationOutcome(
            is_valid=False,
            reason="gateway amount is not numeric",
            raw=validation,
        )

    # Compare in minor-unit-safe integer space to avoid float drift (e.g. 1499.9999).
    if round(validated_amount * 100) != expected_amount * 100:
        return ValidationOutcome(
            is_valid=False,
            reason=(
                f"amount mismatch: gateway charged {validated_amount} "
                f"{validation.get('currency', '')}, expected {expected_amount} "
                f"{expected_currency}"
            ),
            raw=validation,
            validated_amount=validated_amount,
            validated_currency=str(validation.get("currency", "")),
        )

    currency = str(validation.get("currency", "")).upper()
    if currency != expected_currency.upper():
        return ValidationOutcome(
            is_valid=False,
            reason=f"currency mismatch: {currency or 'missing'}, expected {expected_currency}",
            raw=validation,
            validated_amount=validated_amount,
            validated_currency=currency,
        )

    return ValidationOutcome(
        is_valid=True,
        reason="validated",
        raw=validation,
        validated_amount=validated_amount,
        validated_currency=currency,
    )
