


def test_update_profile_requires_authentication(client, registration_payload):
    assert client.put("/auth/update-profile", json={"full_name": "New"}).status_code == 401


def test_update_profile_changes_name_and_phone(client, confirmed_client, client_login):
    response = client.put(
        "/auth/update-profile",
        json={"full_name": "Ayesha R. Chowdhury", "phone_number": "01999999999"},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["full_name"] == "Ayesha R. Chowdhury"
    assert body["phone_number"] == "01999999999"
    # Unspecified fields are left alone.
    assert body["email"] == "ayesha@example.com"


def test_update_profile_with_no_fields_is_a_noop(client, confirmed_client, client_login):
    before = client.get("/auth/me").json()
    response = client.put("/auth/update-profile", json={})
    assert response.status_code == 200
    assert response.json()["full_name"] == before["full_name"]


def test_update_profile_ignores_null_values(client, confirmed_client, client_login):
    before = client.get("/auth/me").json()
    response = client.put(
        "/auth/update-profile", json={"full_name": None, "phone_number": None}
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == before["full_name"]


def test_update_profile_rejects_overlong_phone(client, confirmed_client, client_login):
    response = client.put("/auth/update-profile", json={"phone_number": "1" * 17})
    assert response.status_code == 422


def test_update_profile_does_not_allow_status_change(
    client, confirmed_client, client_login
):
    response = client.put("/auth/update-profile", json={"status": "cancelled"})
    # `status` is not part of UpdateProfileRequest; Pydantic ignores unknown keys,
    # so the account must remain confirmed.
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_update_profile_does_not_allow_email_change(
    client, confirmed_client, client_login
):
    client.put("/auth/update-profile", json={"email": "hijack@example.com"})
    assert client.get("/auth/me").json()["email"] == "ayesha@example.com"


def test_update_password_requires_authentication(anonymous_client):
    response = anonymous_client.put(
        "/auth/update-password",
        json={"current_password": "secret123", "new_password": "newsecret1"},
    )
    assert response.status_code == 401


def test_update_password_rejects_wrong_current_password(
    client, confirmed_client, client_login
):
    response = client.put(
        "/auth/update-password",
        json={"current_password": "wrong", "new_password": "newsecret1"},
    )
    assert response.status_code == 401


def test_update_password_rejects_short_new_password(
    client, confirmed_client, client_login
):
    response = client.put(
        "/auth/update-password",
        json={"current_password": "secret123", "new_password": "short"},
    )
    assert response.status_code == 422


def test_update_password_changes_the_credential(client, confirmed_client, client_login):
    response = client.put(
        "/auth/update-password",
        json={"current_password": "secret123", "new_password": "newsecret1"},
    )
    assert response.status_code == 200

    client.post("/auth/logout")
    assert client.post(
        "/auth/login", json={"email": "ayesha@example.com", "password": "secret123"}
    ).status_code == 401
    assert client.post(
        "/auth/login", json={"email": "ayesha@example.com", "password": "newsecret1"}
    ).status_code == 200


def test_passwords_are_argon2id_hashed(client, registration_payload, engine):
    from uuid import UUID

    from sqlmodel import Session

    from app.models import Alumna

    body = client.post("/auth/register", json=registration_payload).json()

    # Inspect the raw column to confirm no plaintext is stored.
    with Session(engine) as session:
        stored = session.get(Alumna, UUID(body["uuid"]))
        assert stored.password_hash != "secret123"
        assert stored.password_hash.startswith("$argon2id$")


def test_same_password_hashes_differently_per_user(client, registration_payload, engine):
    """Salt must make hashes unique so identical passwords are not linkable."""
    from sqlmodel import Session, select

    from app.models import Alumna

    client.post("/auth/register", json={**registration_payload, "email": "a@example.com"})
    client.post("/auth/register", json={**registration_payload, "email": "b@example.com"})

    with Session(engine) as session:
        hashes = list(session.scalars(select(Alumna.password_hash)).all())

    assert len(hashes) == 2
    assert hashes[0] != hashes[1]