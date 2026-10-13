import json

import pytest

from app import models  # noqa: F401
from app.services import sslcommerz
from app.settings import settings


def test_initiate_requires_authentication(client, gateway_configured, fake_gateway):
    assert client.post("/payments/initiate").status_code == 401


def test_initiate_points_success_url_at_the_api_not_the_frontend(
    client, client_login, gateway_configured, fake_gateway
):
    """Regression guard: success_url used to be the frontend, so the backend
    callback that performs server-side validation never ran."""
    client.post("/payments/initiate")
    call = fake_gateway["session_calls"][0]

    assert call["success_url"] == f"{settings.api_url}/payments/callback"
    assert "/payments/callback" in call["success_url"]
    assert "frontend_url" not in call["success_url"]


def test_initiate_sets_a_separate_ipn_url(client, client_login, gateway_configured, fake_gateway):
    client.post("/payments/initiate")
    assert fake_gateway["session_calls"][0]["ipn_url"] == f"{settings.api_url}/payments/ipn"


def test_initiate_cancel_url_points_at_the_frontend(
    client, client_login, gateway_configured, fake_gateway
):
    client.post("/payments/initiate")
    assert fake_gateway["session_calls"][0]["cancel_url"].startswith(settings.frontend_url)


def test_fee_comes_from_settings(client, client_login, gateway_configured, fake_gateway, monkeypatch):
    monkeypatch.setattr(settings, "event_fee_bdt", 2500)
    client.post("/payments/initiate")
    assert client.get("/payments/me").json()[0]["amount"] == 2500
    assert fake_gateway["session_calls"][0]["amount"] == 2500


def test_initiate_returns_gateway_url(client, client_login, gateway_configured, fake_gateway):
    response = client.post("/payments/initiate")
    assert response.status_code == 200

    body = response.json()
    assert body["transaction_reference"].startswith("MPSC50-")
    assert body["gateway_url"].startswith("https://")
    assert body["session_key"]


def test_initiate_creates_an_unpaid_payment(
    client, client_login, gateway_configured, fake_gateway
):
    response = client.post("/payments/initiate")
    payments = client.get("/payments/me").json()

    assert len(payments) == 1
    assert payments[0]["status"] == "unpaid"
    assert payments[0]["transaction_reference"] == response.json()[
        "transaction_reference"
    ]


def test_initiate_amount_is_server_side_not_client_supplied(
    client, client_login, gateway_configured, fake_gateway
):
    client.post("/payments/initiate")
    payments = client.get("/payments/me").json()
    assert payments[0]["amount"] == settings.event_fee_bdt


def test_initiate_passes_redirect_urls_from_settings(
    client, client_login, gateway_configured, fake_gateway
):
    client.post("/payments/initiate")
    assert fake_gateway["session_calls"][0]["success_url"].startswith(
        settings.api_url
    )


def test_initiate_without_gateway_config_returns_503(client, client_login, monkeypatch):
    """No fake_gateway fixture here: the real service must reject the request
    before any HTTP call is attempted."""
    from app import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "sslcommerz_store_id", None)
    monkeypatch.setattr(settings_module.settings, "sslcommerz_store_password", None)
    response = client.post("/payments/initiate")
    assert response.status_code == 503


def test_list_payments_requires_authentication(client, gateway_configured, fake_gateway):
    assert client.get("/payments/me").status_code == 401


def test_list_payments_is_empty_initially(client, client_login, gateway_configured, fake_gateway):
    assert client.get("/payments/me").json() == []


def test_callback_marks_payment_completed(
    client, client_login, gateway_configured, fake_gateway
):
    initiate = client.post("/payments/initiate").json()

    response = client.post(
        "/payments/callback",
        data={"tran_id": initiate["transaction_reference"]},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "/payment/success" in response.headers["location"]
    assert client.get("/payments/me").json()[0]["status"] == "completed"


def test_callback_ignores_gateway_saying_transaction_does_not_exist(
    client, client_login, gateway_configured, fake_gateway
):
    """A forged success callback must not confirm a payment."""
    initiate = client.post("/payments/initiate").json()
    fake_gateway["validation"]["tran_id"] = "SOME-OTHER-TRANSACTION"

    response = client.post(
        "/payments/callback",
        data={"tran_id": initiate["transaction_reference"]},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "/payment/cancelled" in response.headers["location"]
    assert client.get("/payments/me").json()[0]["status"] == "failed"


def test_callback_marks_payment_failed_when_gateway_says_invalid(
    client, client_login, gateway_configured, fake_gateway
):
    initiate = client.post("/payments/initiate").json()
    fake_gateway["validation"]["status"] = "INVALID"

    response = client.post(
        "/payments/callback",
        data={"tran_id": initiate["transaction_reference"]},
        follow_redirects=False,
    )
    assert "/payment/cancelled" in response.headers["location"]


def test_callback_requires_transaction_reference(
    client, client_login, gateway_configured, fake_gateway
):
    response = client.post("/payments/callback", data={}, follow_redirects=False)
    assert response.status_code == 303
    assert "/payment/cancelled" in response.headers["location"]


def test_callback_404_for_unknown_reference(client, client_login, gateway_configured, fake_gateway):
    response = client.post("/payments/callback", data={"tran_id": "MPSC50-DOESNOTEXIST"})
    assert response.status_code == 404


def test_callback_is_idempotent(client, client_login, gateway_configured, fake_gateway):
    initiate = client.post("/payments/initiate").json()
    client.post(
        "/payments/callback",
        data={"tran_id": initiate["transaction_reference"]},
        follow_redirects=False,
    )
    second = client.post(
        "/payments/callback",
        data={"tran_id": initiate["transaction_reference"]},
        follow_redirects=False,
    )
    assert second.status_code == 303
    assert client.get("/payments/me").json()[0]["status"] == "completed"


def test_manual_confirmation_for_offline_payments(
    client, client_login, gateway_configured, fake_gateway
):
    client.post("/payments/initiate")
    payment_uuid = client.get("/payments/me").json()[0]["uuid"]

    response = client.post(f"/payments/{payment_uuid}/confirm")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_get_single_payment(client, client_login, gateway_configured, fake_gateway):
    client.post("/payments/initiate")
    payment_uuid = client.get("/payments/me").json()[0]["uuid"]

    response = client.get(f"/payments/{payment_uuid}")
    assert response.status_code == 200
    assert response.json()["uuid"] == payment_uuid


def test_manual_confirmation_requires_authentication(client, gateway_configured, fake_gateway):
    import uuid

    assert client.post(f"/payments/{uuid.uuid4()}/confirm").status_code == 401


def test_payments_router_is_registered():
    from app.routes.payment import router

    paths = {route.path for route in router.routes}
    assert "/payments/initiate" in paths
    assert "/payments/callback" in paths


def test_cannot_read_another_alumnas_payment(
    client, registration_payload, admin_headers, gateway_configured, fake_gateway
):
    """Ownership is enforced, so guessing a UUID is not enough."""
    first = client.post("/auth/register", json=registration_payload).json()
    client.patch(
        f"/admin/alumnae/{first['uuid']}/status",
        params={"new_status": "confirmed"},
        headers=admin_headers,
    )
    client.post(
        "/auth/login", json={"email": "ayesha@example.com", "password": "secret123"}
    )
    client.post("/payments/initiate")
    payment_uuid = client.get("/payments/me").json()[0]["uuid"]
    client.post("/auth/logout")

    other = client.post(
        "/auth/register", json={**registration_payload, "email": "other@example.com"}
    ).json()
    client.patch(
        f"/admin/alumnae/{other['uuid']}/status",
        params={"new_status": "confirmed"},
        headers=admin_headers,
    )
    client.post(
        "/auth/login",
        json={"email": "other@example.com", "password": "secret123"},
    )

    assert client.get(f"/payments/{payment_uuid}").status_code == 404


def test_create_payment_session_requires_credentials(monkeypatch):
    import asyncio

    from app import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "sslcommerz_store_id", None)
    monkeypatch.setattr(settings_module.settings, "sslcommerz_store_password", None)

    with pytest.raises(Exception) as excinfo:
        asyncio.run(
            sslcommerz.create_payment_session(
                transaction_reference="T",
                amount=100,
                product_name="P",
                alumna_email="a@e.com",
                alumna_name="A",
                success_url="http://localhost:8000/payments/callback",
                cancel_url="http://localhost:3000/payment/cancelled",
                ipn_url="http://localhost:8000/payments/ipn",
            )
        )
    assert "not configured" in str(excinfo.value)


def test_sandbox_and_live_urls(monkeypatch):
    from app import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "sslcommerz_is_sandbox", True)
    assert sslcommerz._base_url() == "https://sandbox.sslcommerz.com"

    monkeypatch.setattr(settings_module.settings, "sslcommerz_is_sandbox", False)
    assert sslcommerz._base_url() == "https://securepay.sslcommerz.com"


def test_validation_payload_is_serialisable(client, client_login, gateway_configured, fake_gateway):
    initiate = client.post("/payments/initiate").json()
    response = client.post(
        "/payments/ipn",
        data={"tran_id": initiate["transaction_reference"], "status": "VALID"},
    )
    json.dumps(response.json())  # must not raise
    assert "reason" in response.json()


# --- amount / currency verification ---------------------------------------


def _set_validation(fake_gateway, **overrides):
    fake_gateway["validation"].update(overrides)


def test_callback_rejects_an_underpayment(client, client_login, gateway_configured, fake_gateway):
    """The security case: paying 1 BDT must not settle a 1500 BDT fee."""
    initiate = client.post("/payments/initiate").json()
    _set_validation(fake_gateway, amount="1.00")

    response = client.post(
        "/payments/callback",
        data={"tran_id": initiate["transaction_reference"]},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "/payment/cancelled" in response.headers["location"]
    assert client.get("/payments/me").json()[0]["status"] == "failed"


def test_callback_rejects_an_overpayment(client, client_login, gateway_configured, fake_gateway):
    initiate = client.post("/payments/initiate").json()
    _set_validation(fake_gateway, amount="99999.00")

    client.post(
        "/payments/callback",
        data={"tran_id": initiate["transaction_reference"]},
        follow_redirects=False,
    )
    assert client.get("/payments/me").json()[0]["status"] == "failed"


def test_callback_rejects_a_wrong_currency(client, client_login, gateway_configured, fake_gateway):
    initiate = client.post("/payments/initiate").json()
    _set_validation(fake_gateway, currency="USD")

    client.post(
        "/payments/callback",
        data={"tran_id": initiate["transaction_reference"]},
        follow_redirects=False,
    )
    assert client.get("/payments/me").json()[0]["status"] == "failed"


def test_callback_rejects_a_missing_amount(client, client_login, gateway_configured, fake_gateway):
    initiate = client.post("/payments/initiate").json()
    fake_gateway["validation"].pop("amount", None)

    client.post(
        "/payments/callback",
        data={"tran_id": initiate["transaction_reference"]},
        follow_redirects=False,
    )
    assert client.get("/payments/me").json()[0]["status"] == "failed"


def test_callback_accepts_an_exact_amount_despite_float_noise(
    client, client_login, gateway_configured, fake_gateway
):
    """1499.99999 must still count as 1500."""
    initiate = client.post("/payments/initiate").json()
    _set_validation(fake_gateway, amount="1499.99999")

    client.post(
        "/payments/callback",
        data={"tran_id": initiate["transaction_reference"]},
        follow_redirects=False,
    )
    assert client.get("/payments/me").json()[0]["status"] == "completed"


def test_reconcile_validation_accepts_a_matching_payment():
    from app.services.sslcommerz import reconcile_validation

    outcome = reconcile_validation(
        {"status": "VALID", "tran_id": "REF1", "amount": "1500.00", "currency": "BDT"},
        expected_reference="REF1",
        expected_amount=1500,
    )
    assert outcome.is_valid is True


@pytest.mark.parametrize(
    "validation",
    [
        {"status": "INVALID", "tran_id": "REF1", "amount": "1500.00", "currency": "BDT"},
        {"tran_id": "REF1", "amount": "1500.00", "currency": "BDT"},
        {"status": "VALID", "tran_id": "REF2", "amount": "1500.00", "currency": "BDT"},
        {"status": "VALID", "tran_id": "REF1", "amount": "1.00", "currency": "BDT"},
        {"status": "VALID", "tran_id": "REF1", "amount": "1500.00", "currency": "USD"},
        {"status": "VALID", "tran_id": "REF1", "currency": "BDT"},
        {"status": "VALID", "tran_id": "REF1", "amount": "abc", "currency": "BDT"},
    ],
)
def test_reconcile_validation_rejects_mismatches(validation):
    from app.services.sslcommerz import reconcile_validation

    outcome = reconcile_validation(
        validation, expected_reference="REF1", expected_amount=1500
    )
    assert outcome.is_valid is False
    assert outcome.reason


# --- callback redirect behaviour -------------------------------------------


def test_callback_redirects_to_frontend_on_success(
    client, client_login, gateway_configured, fake_gateway
):
    initiate = client.post("/payments/initiate").json()
    response = client.post(
        "/payments/callback",
        data={"tran_id": initiate["transaction_reference"]},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith(f"{settings.frontend_url}/payment/success")


def test_callback_without_reference_redirects_to_cancelled(
    client, client_login, gateway_configured, fake_gateway
):
    response = client.post("/payments/callback", data={}, follow_redirects=False)
    assert response.status_code == 303
    assert "/payment/cancelled" in response.headers["location"]


def test_callback_for_unknown_reference_redirects_rather_than_500(
    client, client_login, gateway_configured, fake_gateway
):
    response = client.post(
        "/payments/callback",
        data={"tran_id": "MPSC50-NOPE"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "/payment/cancelled" in response.headers["location"]


def test_cannot_hit_success_url_without_paying(
    client, client_login, gateway_configured, fake_gateway
):
    """Hitting the callback URL directly must not settle an unpaid payment."""
    initiate = client.post("/payments/initiate").json()
    _set_validation(fake_gateway, status="INVALID")

    client.post(
        "/payments/callback",
        data={"tran_id": initiate["transaction_reference"]},
        follow_redirects=False,
    )
    assert client.get("/payments/me").json()[0]["status"] == "failed"


# --- IPN -------------------------------------------------------------------


def test_ipn_settles_a_valid_payment(client, client_login, gateway_configured, fake_gateway):
    initiate = client.post("/payments/initiate").json()
    response = client.post(
        "/payments/ipn",
        data={"tran_id": initiate["transaction_reference"], "status": "VALID"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert client.get("/payments/me").json()[0]["status"] == "completed"


def test_ipn_rejects_an_underpayment(client, client_login, gateway_configured, fake_gateway):
    initiate = client.post("/payments/initiate").json()
    _set_validation(fake_gateway, amount="0.01")

    response = client.post(
        "/payments/ipn",
        data={"tran_id": initiate["transaction_reference"], "status": "VALID"},
    )
    assert response.json()["status"] == "failed"
    assert client.get("/payments/me").json()[0]["status"] == "failed"


def test_ipn_ignores_a_non_valid_notification(client, client_login, gateway_configured, fake_gateway):
    """A CANCELLED notification must not overwrite an in-flight payment."""
    initiate = client.post("/payments/initiate").json()

    response = client.post(
        "/payments/ipn",
        data={"tran_id": initiate["transaction_reference"], "status": "CANCELLED"},
    )
    assert response.json()["status"] == "unpaid"
    assert client.get("/payments/me").json()[0]["status"] == "unpaid"


def test_ipn_is_idempotent(client, client_login, gateway_configured, fake_gateway):
    initiate = client.post("/payments/initiate").json()
    data = {"tran_id": initiate["transaction_reference"], "status": "VALID"}

    first = client.post("/payments/ipn", data=data).json()
    second = client.post("/payments/ipn", data=data).json()

    assert first["status"] == "completed"
    assert second["status"] == "completed"


def test_ipn_for_unknown_reference_is_acknowledged(
    client, client_login, gateway_configured, fake_gateway
):
    """The gateway retries on non-200, so unknown refs must return 200."""
    response = client.post("/payments/ipn", data={"tran_id": "NOPE", "status": "VALID"})
    assert response.status_code == 200
    assert response.json()["received"] is False


def test_ipn_without_reference(client, client_login, gateway_configured, fake_gateway):
    response = client.post("/payments/ipn", data={})
    assert response.status_code == 200
    assert response.json()["received"] is False


# --- duplicate handling ----------------------------------------------------


def test_reinitiating_reuses_an_unpaid_transaction(
    client, client_login, gateway_configured, fake_gateway
):
    first = client.post("/payments/initiate").json()
    second = client.post("/payments/initiate").json()

    assert first["transaction_reference"] == second["transaction_reference"]
    assert len(client.get("/payments/me").json()) == 1


def test_reinitiating_after_failure_creates_a_new_transaction(
    client, client_login, gateway_configured, fake_gateway
):
    first = client.post("/payments/initiate").json()
    _set_validation(fake_gateway, status="INVALID")
    client.post(
        "/payments/callback",
        data={"tran_id": first["transaction_reference"]},
        follow_redirects=False,
    )

    second = client.post("/payments/initiate").json()
    assert second["transaction_reference"] != first["transaction_reference"]
    assert len(client.get("/payments/me").json()) == 2


def test_initiate_is_blocked_after_a_completed_payment(
    client, client_login, gateway_configured, fake_gateway
):
    initiate = client.post("/payments/initiate").json()
    client.post(
        "/payments/ipn",
        data={"tran_id": initiate["transaction_reference"], "status": "VALID"},
    )

    response = client.post("/payments/initiate")
    assert response.status_code == 409

def test_pending_alumna_can_initiate_payment(
    client, registration_payload, gateway_configured, fake_gateway
):
    """Regression guard for the flow inversion.

    The event flow is register -> pay -> admin approval. Payment used to sit
    behind a confirmed-account check, so a registrant who had just signed up
    and not yet been approved got a 404 on their first attempt to pay.
    """
    client.post("/auth/register", json=registration_payload)

    response = client.post("/payments/initiate")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["gateway_url"]
    assert body["transaction_reference"]


def test_cancelled_alumna_cannot_initiate_payment(
    client, registration_payload, gateway_configured, fake_gateway, admin_headers
):
    """Cancelling must revoke payment access, not just block login."""
    body = client.post("/auth/register", json=registration_payload).json()
    client.patch(
        f"/admin/alumnae/{body['uuid']}/status",
        params={"new_status": "cancelled"},
        headers=admin_headers,
    )

    assert client.post("/payments/initiate").status_code == 404
