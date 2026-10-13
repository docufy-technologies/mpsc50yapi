import os

# Settings are instantiated at import time, so the environment must be primed
# before anything from `app` is imported.
os.environ.setdefault("DATABASE_URI", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_PUBLIC_KEY", "test-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_NAME", "mpsc_access_token")
os.environ.setdefault("ADMIN_SECRET", "test-admin-secret")
os.environ.setdefault("COOKIE_DOMAIN", "")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("DEV_MODE", "1")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401  (registers tables on SQLModel.metadata)
from app.database import get_database_session
from app.main_app import create_app
from app.routes import payment as payment_routes
from app.services import sslcommerz
from app.services.sslcommerz import PaymentSession


@pytest.fixture
def engine():
    # StaticPool is required: an in-memory SQLite database lives inside the
    # connection, so every new connection would otherwise get an empty DB.
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def client(engine):
    app = create_app(create_tables=False)

    def override_session():
        with Session(bind=engine) as session:
            yield session

    app.dependency_overrides[get_database_session] = override_session

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def admin_headers():
    return {"X-Admin-Secret": "test-admin-secret"}


@pytest.fixture
def registration_payload():
    return {
        "full_name": "Ayesha Rahman",
        "email": "ayesha@example.com",
        "phone_number": "01712345678",
        "password": "secret123",
        "batch_year": 2010,
        "tee_shirt_size": "M",
    }


@pytest.fixture
def confirmed_client(client, registration_payload, admin_headers):
    """Registers an alumna and approves her, mirroring the real approval flow."""
    body = client.post("/auth/register", json=registration_payload).json()
    client.patch(
        f"/admin/alumnae/{body['uuid']}/status",
        params={"new_status": "confirmed"},
        headers=admin_headers,
    )
    return body


@pytest.fixture
def anonymous_client(client):
    """A `client` with no session cookie.

    POST /auth/register now issues the access cookie (register -> pay -> admin
    approval), so any fixture that registers leaves the shared `client`
    authenticated. Tests that assert 401s need this instead.
    """
    client.cookies.clear()
    return client


@pytest.fixture
def client_login(client, confirmed_client):
    """Logs the confirmed alumna in on the shared `client` session."""
    response = client.post(
        "/auth/login",
        json={"email": "ayesha@example.com", "password": "secret123"},
    )
    assert response.status_code == 200, "fixture login failed"
    return confirmed_client

@pytest.fixture
def fake_gateway(monkeypatch):
    """Replaces the SSLCommerz HTTP calls so the flow can be tested offline."""
    state: dict = {
        "validation": {
            "status": "VALID",
            "tran_id": "",
            "amount": "1500.00",
            "currency": "BDT",
            "validation_date": "2026-10-12T10:00:00",
        },
        "session_calls": [],
        "validation_calls": [],
    }

    async def fake_create(**kwargs):
        state["session_calls"].append(kwargs)
        return PaymentSession(
            gateway_url="https://sandbox.sslcommerz.com/EasyCheckOut/test",
            session_key=f"SESSION-{kwargs['transaction_reference']}",
        )

    async def fake_validate(transaction_reference):
        state["validation_calls"].append(transaction_reference)
        payload = dict(state["validation"])
        payload.setdefault("tran_id", transaction_reference)
        if not payload.get("tran_id"):
            payload["tran_id"] = transaction_reference
        return payload

    monkeypatch.setattr(payment_routes, "create_payment_session", fake_create)
    monkeypatch.setattr(payment_routes, "validate_transaction", fake_validate)
    monkeypatch.setattr(
        sslcommerz,
        "create_payment_session",
        fake_create,
        raising=False,
    )
    return state


@pytest.fixture
def gateway_configured(monkeypatch):
    from app import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "sslcommerz_store_id", "store123")
    monkeypatch.setattr(
        settings_module.settings, "sslcommerz_store_password", "pass123"
    )
    return True
