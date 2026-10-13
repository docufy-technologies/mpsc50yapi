import uuid


def test_register_creates_pending_account(client, registration_payload):
    response = client.post("/auth/register", json=registration_payload)
    assert response.status_code == 201

    body = response.json()
    assert body["status"] == "pending"
    assert body["email"] == registration_payload["email"]
    assert body["profile"]["batch_year"] == 2010
    assert body["profile"]["tee_shirt_size"] == "M"
    assert body["profile"]["reg_code"]
    # The password hash must never be echoed back.
    assert "password_hash" not in body


def test_register_normalizes_email_to_lowercase(client, registration_payload):
    registration_payload["email"] = "AyEsHa@Example.COM"
    response = client.post("/auth/register", json=registration_payload)
    assert response.status_code == 201
    assert response.json()["email"] == "ayesha@example.com"


def test_register_rejects_duplicate_email(client, registration_payload):
    client.post("/auth/register", json=registration_payload)
    response = client.post("/auth/register", json=registration_payload)
    assert response.status_code == 409
    assert "already registered" in response.json()["detail"]


def test_register_rejects_duplicate_reg_code(client, registration_payload):
    first = {**registration_payload, "email": "one@example.com", "reg_code": "SHARED1"}
    second = {**registration_payload, "email": "two@example.com", "reg_code": "SHARED1"}

    assert client.post("/auth/register", json=first).status_code == 201
    response = client.post("/auth/register", json=second)
    assert response.status_code == 409
    assert "registration code" in response.json()["detail"]


def test_register_persists_nested_collections(client, registration_payload):
    payload = {
        **registration_payload,
        "student_id": "S-42",
        "work_profile": {
            "organization_name": "Docufy",
            "designation": "Engineer",
            "department_or_division": "Engineering",
        },
        "address": {
            "street_address": "Road 1",
            "city": "Dhaka",
            "state_or_province": "Dhaka",
            "postal_code": "1207",
            "country": "Bangladesh",
        },
        "acquaintances": [
            {"full_name": "Karim", "relation": "Friend", "age_group": "adult"},
            {"full_name": "Ayesha Jr", "relation": "Child", "age_group": "child"},
        ],
    }

    body = client.post("/auth/register", json=payload).json()

    assert body["profile"]["student_id"] == "S-42"
    assert body["profile"]["work_profile"]["organization_name"] == "Docufy"
    assert body["profile"]["address"]["city"] == "Dhaka"
    assert len(body["acquaintances"]) == 2
    assert {a["age_group"] for a in body["acquaintances"]} == {"adult", "child"}


def test_register_allows_optional_sections_to_be_omitted(client, registration_payload):
    body = client.post("/auth/register", json=registration_payload).json()
    assert body["profile"]["work_profile"] is None
    assert body["profile"]["address"] is None
    assert body["acquaintances"] == []


def test_register_rejects_short_password(client, registration_payload):
    response = client.post(
        "/auth/register", json={**registration_payload, "password": "short"}
    )
    assert response.status_code == 422


def test_register_rejects_invalid_email(client, registration_payload):
    response = client.post(
        "/auth/register", json={**registration_payload, "email": "not-an-email"}
    )
    assert response.status_code == 422


def test_register_rejects_out_of_range_batch_year(client, registration_payload):
    response = client.post(
        "/auth/register", json={**registration_payload, "batch_year": 1900}
    )
    assert response.status_code == 422


def test_register_rejects_future_batch_year(client, registration_payload):
    response = client.post(
        "/auth/register", json={**registration_payload, "batch_year": 3000}
    )
    assert response.status_code == 422


def test_register_rejects_invalid_tee_shirt_size(client, registration_payload):
    response = client.post(
        "/auth/register", json={**registration_payload, "tee_shirt_size": "XXXXL"}
    )
    assert response.status_code == 422


def test_register_rejects_invalid_age_group(client, registration_payload):
    payload = {
        **registration_payload,
        "acquaintances": [
            {"full_name": "X", "relation": "Friend", "age_group": "teenager"}
        ],
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 422


def test_generated_reg_codes_are_unique(client, registration_payload):
    first = client.post(
        "/auth/register", json={**registration_payload, "email": "a@example.com"}
    ).json()
    second = client.post(
        "/auth/register", json={**registration_payload, "email": "b@example.com"}
    ).json()

    assert first["profile"]["reg_code"] != second["profile"]["reg_code"]
    assert len(first["profile"]["reg_code"]) == 12


def test_registered_uuid_is_a_uuid(client, registration_payload):
    body = client.post("/auth/register", json=registration_payload).json()
    assert uuid.UUID(body["uuid"])


def test_register_issues_access_cookie(client, registration_payload):
    """The event flow is register -> pay -> admin approval, so a pending
    alumna must leave registration with a working session."""
    response = client.post("/auth/register", json=registration_payload)
    assert response.status_code == 201
    assert client.cookies.get("mpsc_access_token")

    # The cookie is usable straight away, without a separate login.
    assert client.get("/auth/me").status_code == 200


def test_register_cookie_is_httponly(client, registration_payload):
    response = client.post("/auth/register", json=registration_payload)
    header = response.headers["set-cookie"].lower()
    assert "mpsc_access_token=" in header
    assert "httponly" in header


def test_register_accepts_academic_group(client, registration_payload):
    payload = {**registration_payload, "academic_group": "science"}
    body = client.post("/auth/register", json=payload).json()
    assert body["profile"]["academic_group"] == "science"


def test_register_defaults_academic_group_to_none(client, registration_payload):
    body = client.post("/auth/register", json=registration_payload).json()
    assert body["profile"]["academic_group"] is None


def test_register_rejects_unknown_academic_group(client, registration_payload):
    payload = {**registration_payload, "academic_group": "underwater-basketweaving"}
    assert client.post("/auth/register", json=payload).status_code == 422
