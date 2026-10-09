"""Run with:  pytest -v"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import User
from app.security import hash_password

# Each test gets a fresh in-memory database
engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


SIGNUP = {
    "email": "rahim@example.com", "password": "password123", "full_name": "Rahim Uddin",
    "batch_year": 1990, "department": "CSE", "phone": "01700000000",
}


def signup_and_login(client, **overrides):
    data = {**SIGNUP, **overrides}
    assert client.post("/auth/signup", json=data).status_code == 201
    r = client.post("/auth/login", data={"username": data["email"], "password": data["password"]})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def make_admin_headers(client):
    with TestingSession() as db:
        db.add(User(email="admin@example.com", password_hash=hash_password("adminpass1"), is_admin=True))
        db.commit()
    r = client.post("/auth/login", data={"username": "admin@example.com", "password": "adminpass1"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def create_event(client, admin, **overrides):
    body = {
        "title": "Golden Jubilee Reunion", "venue": "University Hall", "event_date": "2027-01-15",
        "registration_deadline": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "fee_per_person": "1500", **overrides,
    }
    r = client.post("/events/", json=body, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def test_signup_login_and_me(client):
    headers = signup_and_login(client)
    me = client.get("/auth/me", headers=headers).json()
    assert me["email"] == "rahim@example.com"
    assert me["profile"]["batch_year"] == 1990


def test_duplicate_email_and_wrong_password(client):
    signup_and_login(client)
    assert client.post("/auth/signup", json=SIGNUP).status_code == 409
    bad = client.post("/auth/login", data={"username": SIGNUP["email"], "password": "wrongwrong"})
    assert bad.status_code == 401


def test_protected_routes_need_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.post("/registrations", json={"event_id": 1}).status_code == 401


def test_only_admin_can_create_events(client):
    headers = signup_and_login(client)
    r = client.post("/events/", json={"title": "x"}, headers=headers)
    assert r.status_code in (403, 422)
    admin = make_admin_headers(client)
    create_event(client, admin)
    assert len(client.get("/events/").json()) == 1


def test_registration_with_guests_and_total(client):
    admin = make_admin_headers(client)
    event = create_event(client, admin)
    headers = signup_and_login(client)
    r = client.post("/registrations", headers=headers, json={
        "event_id": event["id"], "tshirt_size": "L",
        "guests": [{"full_name": "Wife", "relation": "spouse"}, {"full_name": "Kid", "age_group": "child"}],
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending" and body["reg_code"].startswith("ALM-")
    assert float(body["total_amount"]) == 4500.0  # 3 people x 1500
    assert len(body["guests"]) == 2


def test_cannot_register_twice(client):
    admin = make_admin_headers(client)
    event = create_event(client, admin)
    headers = signup_and_login(client)
    assert client.post("/registrations", headers=headers, json={"event_id": event["id"]}).status_code == 201
    assert client.post("/registrations", headers=headers, json={"event_id": event["id"]}).status_code == 409


def test_waitlist_when_full_then_cancel_and_reregister(client):
    admin = make_admin_headers(client)
    event = create_event(client, admin, capacity=1)
    h1 = signup_and_login(client)
    h2 = signup_and_login(client, email="karim@example.com")
    assert client.post("/registrations", headers=h1, json={"event_id": event["id"]}).json()["status"] == "pending"
    second = client.post("/registrations", headers=h2, json={"event_id": event["id"]}).json()
    assert second["status"] == "waitlisted"
    # first person cancels, then re-registers successfully
    mine = client.get("/registrations/me", headers=h1).json()[0]
    assert client.post(f"/registrations/{mine['id']}/cancel", headers=h1).json()["status"] == "cancelled"
    again = client.post("/registrations", headers=h1, json={"event_id": event["id"]})
    assert again.status_code == 201 and again.json()["status"] == "pending"


def test_closed_registration_rejected(client):
    admin = make_admin_headers(client)
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    event = create_event(client, admin, registration_deadline=past)
    headers = signup_and_login(client)
    assert client.post("/registrations", headers=headers, json={"event_id": event["id"]}).status_code == 400


def test_admin_confirms_payment(client):
    admin = make_admin_headers(client)
    event = create_event(client, admin)
    headers = signup_and_login(client)
    reg = client.post("/registrations", headers=headers, json={"event_id": event["id"]}).json()
    r = client.patch(f"/admin/registrations/{reg['id']}/payment", headers=admin,
                     json={"payment_status": "paid", "payment_method": "bKash", "transaction_ref": "TX123"})
    assert r.json()["status"] == "confirmed" and r.json()["payment_status"] == "paid"
    # normal users can't use admin routes
    assert client.get("/admin/registrations", headers=headers).status_code == 403
    assert len(client.get("/admin/registrations", headers=admin).json()) == 1
