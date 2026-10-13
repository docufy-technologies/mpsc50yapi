def test_list_requires_admin_secret(client, registration_payload):
    client.post("/auth/register", json=registration_payload)
    assert client.get("/admin/alumnae").status_code == 401


def test_list_rejects_wrong_admin_secret(client):
    response = client.get("/admin/alumnae", headers={"X-Admin-Secret": "nope"})
    assert response.status_code == 401


def test_list_with_admin_secret(client, registration_payload):
    client.post("/auth/register", json=registration_payload)
    response = client.get("/admin/alumnae", headers={"X-Admin-Secret": "test-admin-secret"})
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_admin_can_see_pending_accounts_that_cannot_log_in(
    client, registration_payload
):
    """Registration creates a pending account; the admin list is the only way
    to see and approve it."""
    client.post("/auth/register", json=registration_payload)

    pending = client.get(
        "/admin/alumnae",
        params={"status": "pending"},
        headers={"X-Admin-Secret": "test-admin-secret"},
    ).json()
    assert len(pending) == 1
    assert pending[0]["status"] == "pending"


def test_status_filter_rejects_unknown_value(client):
    response = client.get(
        "/admin/alumnae",
        params={"status": "bogus"},
        headers={"X-Admin-Secret": "test-admin-secret"},
    )
    assert response.status_code == 422


def test_status_update_confirms_account(client, registration_payload, admin_headers):
    body = client.post("/auth/register", json=registration_payload).json()

    # Registration itself issues the access cookie, so the alumna can pay
    # before approval. Approval is the last step, not a login prerequisite.
    assert client.post(
        "/auth/login", json={"email": "ayesha@example.com", "password": "secret123"}
    ).status_code == 200

    approved = client.patch(
        f"/admin/alumnae/{body['uuid']}/status",
        params={"new_status": "confirmed"},
        headers=admin_headers,
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "confirmed"

    assert client.post(
        "/auth/login", json={"email": "ayesha@example.com", "password": "secret123"}
    ).status_code == 200


def test_status_update_requires_secret(client, registration_payload):
    body = client.post("/auth/register", json=registration_payload).json()
    response = client.patch(
        f"/admin/alumnae/{body['uuid']}/status", params={"new_status": "confirmed"}
    )
    assert response.status_code == 401


def test_status_update_rejects_invalid_status(client, registration_payload, admin_headers):
    body = client.post("/auth/register", json=registration_payload).json()
    response = client.patch(
        f"/admin/alumnae/{body['uuid']}/status",
        params={"new_status": "deleted"},
        headers=admin_headers,
    )
    assert response.status_code == 422


def test_status_update_404_for_unknown_uuid(client, admin_headers):
    import uuid

    response = client.patch(
        f"/admin/alumnae/{uuid.uuid4()}/status",
        params={"new_status": "confirmed"},
        headers=admin_headers,
    )
    assert response.status_code == 404


def test_counts_group_by_status(client, registration_payload, admin_headers):
    assert client.get("/admin/alumnae/counts", headers=admin_headers).json() == {
        "pending": 0,
        "confirmed": 0,
        "cancelled": 0,
    }

    first = client.post("/auth/register", json=registration_payload).json()
    client.post(
        "/auth/register", json={**registration_payload, "email": "second@example.com"}
    )
    client.patch(
        f"/admin/alumnae/{first['uuid']}/status",
        params={"new_status": "confirmed"},
        headers=admin_headers,
    )

    counts = client.get("/admin/alumnae/counts", headers=admin_headers).json()
    assert counts == {"pending": 1, "confirmed": 1, "cancelled": 0}


def test_counts_requires_secret(client):
    assert client.get("/admin/alumnae/counts").status_code == 401


def test_admin_list_supports_pagination(client, registration_payload, admin_headers):
    for index in range(5):
        client.post(
            "/auth/register",
            json={**registration_payload, "email": f"user{index}@example.com"},
        )

    page = client.get(
        "/admin/alumnae",
        params={"limit": 2, "offset": 0},
        headers=admin_headers,
    ).json()
    assert len(page) == 2

    second_page = client.get(
        "/admin/alumnae",
        params={"limit": 2, "offset": 2},
        headers=admin_headers,
    ).json()
    assert len(second_page) == 2
    assert page[0]["uuid"] != second_page[0]["uuid"]


def test_admin_list_rejects_out_of_range_limit(client, admin_headers):
    response = client.get(
        "/admin/alumnae", params={"limit": 5000}, headers=admin_headers
    )
    assert response.status_code == 422

# --- Admin panel authentication -------------------------------------------
#
# The panel signs in with POST /admin/login and holds its own cookie. The
# X-Admin-Secret header stays supported so scripted access keeps working.


def test_admin_login_rejects_a_wrong_secret(anonymous_client):
    response = anonymous_client.post(
        "/admin/login", json={"admin_secret": "not-the-secret"}
    )
    assert response.status_code == 401
    assert not anonymous_client.cookies.get("mpsc_admin_token")


def test_admin_login_sets_a_httponly_cookie(client):
    response = client.post("/admin/login", json={"admin_secret": "test-admin-secret"})
    assert response.status_code == 200

    header = response.headers["set-cookie"].lower()
    assert "mpsc_admin_token=" in header
    assert "httponly" in header


def test_admin_cookie_is_separate_from_the_alumna_cookie(
    client, confirmed_client
):
    """A panel session must not clobber an alumna session in the same browser."""
    alumna_cookie = client.cookies.get("mpsc_access_token")

    client.post("/admin/login", json={"admin_secret": "test-admin-secret"})

    assert client.cookies.get("mpsc_access_token") == alumna_cookie
    assert client.cookies.get("mpsc_admin_token")


def test_admin_cookie_authorizes_the_panel(client, registration_payload):
    client.post("/auth/register", json=registration_payload)
    client.post("/admin/login", json={"admin_secret": "test-admin-secret"})

    assert client.get("/admin/alumnae").status_code == 200


def test_admin_alumnae_reject_an_alumna_cookie(client, registration_payload):
    """Regression guard: an alumna session must never be treated as an admin one."""
    client.post("/auth/register", json=registration_payload)

    response = client.get("/admin/alumnae")

    assert response.status_code == 401
    assert "Admin authentication required" in response.json()["detail"]


def test_admin_alumnae_reject_an_alumna_token_in_the_admin_cookie(
    client, registration_payload
):
    """The real escalation attempt: a valid alumna token pasted into the admin
    cookie slot. Signature and expiry both check out, so only the `admin` claim
    stops it."""
    from app.services.token import encode_access_token

    body = client.post("/auth/register", json=registration_payload).json()
    client.cookies.set(
        "mpsc_admin_token", encode_access_token({"uuid": body["uuid"]})
    )

    response = client.get("/admin/alumnae")

    assert response.status_code == 401
    assert "not an admin session" in response.json()["detail"]


def test_admin_session_requires_authentication(anonymous_client):
    assert anonymous_client.get("/admin/session").status_code == 401


def test_admin_session_confirms_a_valid_cookie(client):
    client.post("/admin/login", json={"admin_secret": "test-admin-secret"})
    assert client.get("/admin/session").json() == {"authenticated": True}


def test_admin_logout_clears_the_cookie(client):
    client.post("/admin/login", json={"admin_secret": "test-admin-secret"})
    assert client.post("/admin/logout").status_code == 200
    assert client.get("/admin/alumnae").status_code == 401


def test_admin_secret_header_still_works_without_a_cookie(
    anonymous_client, registration_payload
):
    anonymous_client.post("/auth/register", json=registration_payload)
    assert anonymous_client.get(
        "/admin/alumnae", headers={"X-Admin-Secret": "test-admin-secret"}
    ).status_code == 200


def test_admin_login_fails_closed_when_secret_is_unset(client, monkeypatch):
    """An unconfigured deployment must never accept an empty secret."""
    from app import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "admin_secret", "")

    assert client.post(
        "/admin/login", json={"admin_secret": ""}
    ).status_code == 422  # rejected by min_length before comparison
    assert client.post("/admin/login", json={"admin_secret": "anything"}).status_code == 401


def test_admin_panel_rejects_an_expired_cookie(client):
    from app.services.token import encode_access_token

    client.cookies.set(
        "mpsc_admin_token",
        encode_access_token({"admin": True}, expiry_seconds=-60),
    )
    assert client.get("/admin/alumnae").status_code == 401


# --- Payment visibility ----------------------------------------------------
#
# With register -> pay -> admin approval, the panel's main job is answering
# "has she paid?". The alumnae listing carries a payment summary for that.


def test_alumna_rows_report_unpaid_by_default(client, admin_headers, registration_payload):
    client.post("/auth/register", json=registration_payload)

    body = client.get("/admin/alumnae", headers=admin_headers).json()[0]

    assert body["payment"]["has_paid"] is False
    assert body["payment"]["latest_status"] == "unpaid"
    assert body["payment"]["amount"] is None


def test_alumna_rows_report_a_completed_payment(
    client, admin_headers, registration_payload, gateway_configured, fake_gateway
):
    """A completed payment shows up on the admin listing, which is the whole
    point of the summary."""
    client.post("/auth/register", json=registration_payload)
    initiate = client.post("/payments/initiate").json()
    client.post("/payments/callback", data={"tran_id": initiate["transaction_reference"]})

    body = client.get("/admin/alumnae", headers=admin_headers).json()[0]

    assert body["payment"]["has_paid"] is True
    assert body["payment"]["latest_status"] == "completed"
    assert body["payment"]["amount"] == 1500
    assert body["payment"]["transaction_reference"] == initiate["transaction_reference"]


def test_failed_payment_is_not_reported_as_paid(
    client, admin_headers, registration_payload, gateway_configured, fake_gateway
):
    client.post("/auth/register", json=registration_payload)
    initiate = client.post("/payments/initiate").json()
    fake_gateway["validation"]["status"] = "FAILED"
    client.post("/payments/callback", data={"tran_id": initiate["transaction_reference"]})

    body = client.get("/admin/alumnae", headers=admin_headers).json()[0]

    assert body["payment"]["has_paid"] is False
    assert body["payment"]["latest_status"] == "failed"


def test_alumna_own_view_does_not_leak_payment_summary(client, client_login):
    """The summary is an admin projection; /auth/me leaves it empty."""
    assert client.get("/auth/me").json()["payment"] == {
        "has_paid": False,
        "latest_status": "unpaid",
        "amount": None,
        "transaction_reference": None,
        "paid_at": None,
    }


def test_payment_summary_reports_the_latest_payment(
    client, admin_headers, registration_payload, gateway_configured, fake_gateway
):
    """Re-initiating after a failure creates a second payment; the panel shows
    the most recent one, not the first."""
    client.post("/auth/register", json=registration_payload)
    first = client.post("/payments/initiate").json()
    fake_gateway["validation"]["status"] = "FAILED"
    client.post("/payments/callback", data={"tran_id": first["transaction_reference"]})

    second = client.post("/payments/initiate").json()
    assert second["transaction_reference"] != first["transaction_reference"]

    fake_gateway["validation"]["status"] = "VALID"
    client.post("/payments/callback", data={"tran_id": second["transaction_reference"]})

    body = client.get("/admin/alumnae", headers=admin_headers).json()[0]
    assert body["payment"]["has_paid"] is True
    assert body["payment"]["transaction_reference"] == second["transaction_reference"]
