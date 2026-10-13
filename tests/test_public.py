def test_event_information_is_public(client):
    response = client.get("/public/event")
    assert response.status_code == 200

    body = response.json()
    assert body["established_year"] == 1976
    assert body["celebration_year"] == 2026
    assert body["participation_fee_bdt"] > 0


def test_statistics_start_at_zero(client):
    assert client.get("/public/statistics").json() == {
        "confirmed_alumnae": 0,
        "total_registrations": 0,
        "batch_years_covered": 0,
    }


def test_statistics_count_registrations(client, registration_payload):
    client.post("/auth/register", json=registration_payload)
    stats = client.get("/public/statistics").json()
    assert stats["total_registrations"] == 1
    assert stats["confirmed_alumnae"] == 0


def test_statistics_count_confirmed_separately(client, client_login):
    stats = client.get("/public/statistics").json()
    assert stats["total_registrations"] == 1
    assert stats["confirmed_alumnae"] == 1
    assert stats["batch_years_covered"] == 1


def test_statistics_count_distinct_batch_years(client, registration_payload):
    client.post("/auth/register", json={**registration_payload, "email": "a@e.com"})
    client.post(
        "/auth/register",
        json={**registration_payload, "email": "b@e.com", "batch_year": 2011},
    )
    client.post(
        "/auth/register",
        json={**registration_payload, "email": "c@e.com", "batch_year": 2011},
    )

    stats = client.get("/public/statistics").json()
    assert stats["total_registrations"] == 3
    assert stats["batch_years_covered"] == 2


def test_statistics_expose_no_personal_data(client, registration_payload):
    client.post("/auth/register", json=registration_payload)
    body = client.get("/public/statistics").text
    assert "ayesha@example.com" not in body
    assert "Ayesha Rahman" not in body
    assert "01712345678" not in body


def test_health_check(client):
    assert client.get("/").status_code == 200


def test_openapi_schema_is_generated(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/auth/register" in paths
    assert "/admin/alumnae" in paths
    assert "/public/event" in paths


def test_event_fee_matches_the_configured_fee(client, monkeypatch):
    """The advertised price must not drift from the charged one."""
    from app import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "event_fee_bdt", 2500)

    assert client.get("/public/event").json()["participation_fee_bdt"] == 2500
