def _login(client, email="ayesha@example.com", password="secret123"):
    return client.post(
        "/auth/login", json={"email": email, "password": password}
    )


def test_login_succeeds_for_confirmed_account(client, confirmed_client):
    response = _login(client)
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_login_sets_httponly_cookie(client, confirmed_client):
    response = _login(client)
    cookie_header = response.headers["set-cookie"]
    assert "mpsc_access_token=" in cookie_header
    assert "HttpOnly" in cookie_header


def test_login_cookie_in_dev_mode_is_not_secure(client, confirmed_client):
    """Secure/SameSite=None over plain http would make the browser drop the
    cookie, so DEV_MODE must relax both."""
    cookie_header = _login(client).headers["set-cookie"]
    assert "Secure" not in cookie_header
    assert "SameSite=none" not in cookie_header


def test_login_is_case_insensitive_on_email(client, confirmed_client):
    assert _login(client, email="AYESHA@EXAMPLE.COM").status_code == 200


def test_login_rejects_wrong_password(client, confirmed_client):
    response = _login(client, password="wrongpassword")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


def test_login_rejects_unknown_email(client, confirmed_client):
    response = _login(client, email="nobody@example.com")
    assert response.status_code == 401


def test_login_allows_pending_account(client, registration_payload):
    """An alumna pays before an admin approves her, so she must be able to
    return and log in while still `pending`."""
    client.post("/auth/register", json=registration_payload)
    response = _login(client)
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_login_blocks_cancelled_account(client, confirmed_client, admin_headers):
    client.patch(
        f"/admin/alumnae/{confirmed_client['uuid']}/status",
        params={"new_status": "cancelled"},
        headers=admin_headers,
    )
    assert _login(client).status_code == 403


def test_login_never_returns_password_hash(client, confirmed_client):
    body = _login(client).json()
    assert "password_hash" not in body


def test_me_requires_authentication(anonymous_client):
    assert anonymous_client.get("/auth/me").status_code == 401


def test_me_returns_profile_for_authenticated_alumna(client, confirmed_client):
    _login(client)
    body = client.get("/auth/me").json()
    assert body["uuid"] == confirmed_client["uuid"]
    assert body["status"] == "confirmed"


def test_me_is_401_after_logout(client, confirmed_client):
    _login(client)
    assert client.post("/auth/logout").status_code == 200
    assert client.get("/auth/me").status_code == 401


def test_logout_clears_cookie_with_matching_path(client, confirmed_client):
    _login(client)
    cookie_header = client.post("/auth/logout").headers["set-cookie"]
    assert "mpsc_access_token=" in cookie_header
    assert "Max-Age=0" in cookie_header
    assert "Path=/" in cookie_header


def test_verify_token_accepts_valid_cookie(client, confirmed_client):
    _login(client)
    response = client.get("/auth/verify-token")
    assert response.status_code == 200
    assert response.json()["message"] == "Validated"


def test_verify_token_rejects_missing_cookie(anonymous_client):
    assert anonymous_client.get("/auth/verify-token").status_code == 401


def test_verify_token_rejects_token_for_cancelled_account(
    client, confirmed_client, admin_headers
):
    """A signature-valid token must not validate a dead account."""
    _login(client)
    client.patch(
        f"/admin/alumnae/{confirmed_client['uuid']}/status",
        params={"new_status": "cancelled"},
        headers=admin_headers,
    )
    assert client.get("/auth/verify-token").status_code == 401


def test_verify_token_rejects_tampered_token(client, confirmed_client):
    _login(client)
    client.cookies.set("mpsc_access_token", "not.a.jwt")
    assert client.get("/auth/verify-token").status_code == 401


def test_refresh_token_reissues_for_valid_session(client, confirmed_client):
    _login(client)
    response = client.post("/auth/refresh-token")
    assert response.status_code == 200
    assert response.json()["access_token"]
    # The refreshed session must still work.
    assert client.get("/auth/me").status_code == 200


def test_refresh_token_requires_a_cookie(anonymous_client):
    assert anonymous_client.post("/auth/refresh-token").status_code == 401


def test_refresh_token_rejects_long_expired_token(client, confirmed_client):
    from app.services.token import encode_access_token

    _login(client)
    long_dead = encode_access_token(
        {"uuid": confirmed_client["uuid"]}, expiry_seconds=-60 * 60 * 24 * 30
    )
    client.cookies.set("mpsc_access_token", long_dead)
    response = client.post("/auth/refresh-token")
    assert response.status_code == 401
    assert "refresh window" in response.json()["detail"]


def test_refresh_token_accepts_recently_expired_token(client, confirmed_client):
    from app.services.token import encode_access_token

    _login(client)
    just_expired = encode_access_token(
        {"uuid": confirmed_client["uuid"]}, expiry_seconds=-60
    )
    client.cookies.set("mpsc_access_token", just_expired)
    assert client.post("/auth/refresh-token").status_code == 200