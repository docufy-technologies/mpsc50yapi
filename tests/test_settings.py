import pytest

from app.settings import Settings


def _settings(**overrides):
    base = {
        "DATABASE_URI": "sqlite://",
        "JWT_SECRET_KEY": "k",
        "JWT_PUBLIC_KEY": "k",
        "JWT_ALGORITHM": "HS256",
        "ACCESS_TOKEN_NAME": "mpsc_access_token",
        "ADMIN_SECRET": "s",
        "COOKIE_DOMAIN": "mpsc50years.docufybd.com",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_production_cookie_is_secure_and_cross_site(monkeypatch):
    monkeypatch.delenv("DEV_MODE", raising=False)
    config = _settings().access_token_config("token", 86400)

    assert config["httponly"] is True
    assert config["secure"] is True
    assert config["samesite"] == "none"
    assert config["domain"] == "mpsc50years.docufybd.com"


def test_dev_cookie_avoids_secure_flag(monkeypatch):
    """Secure cookies are dropped by the browser over plain http://localhost,
    which made local login impossible."""
    monkeypatch.setenv("DEV_MODE", "1")
    config = _settings().access_token_config("token", 86400)

    assert config["secure"] is False
    assert config["samesite"] == "lax"
    assert config["domain"] is None


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_dev_mode_truthy_values(monkeypatch, value):
    monkeypatch.setenv("DEV_MODE", value)
    assert _settings().dev_mode is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", ""])
def test_dev_mode_falsy_values(monkeypatch, value):
    monkeypatch.setenv("DEV_MODE", value)
    assert _settings().dev_mode is False


def test_dev_mode_unset_is_production(monkeypatch):
    monkeypatch.delenv("DEV_MODE", raising=False)
    assert _settings().dev_mode is False


def test_dev_mode_is_read_from_the_env_file(monkeypatch, tmp_path):
    """Regression guard: dev_mode was originally an os.getenv lookup, which
    silently ignored DEV_MODE in .env because pydantic-settings loads the file
    into the Settings object rather than into os.environ."""
    monkeypatch.delenv("DEV_MODE", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DATABASE_URI=sqlite://",
                "JWT_SECRET_KEY=k",
                "JWT_PUBLIC_KEY=k",
                "JWT_ALGORITHM=HS256",
                "ACCESS_TOKEN_NAME=mpsc_access_token",
                "ADMIN_SECRET=s",
                "DEV_MODE=1",
            ]
        )
    )

    settings = Settings(_env_file=env_file)  # type: ignore[arg-type]

    assert settings.dev_mode is True
    assert settings.access_token_config("token", 60)["secure"] is False


def test_delete_cookie_matches_set_cookie_in_production(monkeypatch):
    """delete_cookie needs the same path and domain, otherwise the browser
    keeps the original cookie and logout does nothing."""
    monkeypatch.delenv("DEV_MODE", raising=False)
    settings = _settings()

    set_config = settings.access_token_config("token", 86400)
    delete_config = settings.delete_cookie_config(settings.access_token_name)

    assert delete_config["path"] == set_config["path"]
    assert delete_config["domain"] == set_config["domain"]


def test_delete_cookie_matches_set_cookie_in_dev(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "1")
    settings = _settings()

    set_config = settings.access_token_config("token", 86400)
    delete_config = settings.delete_cookie_config(settings.access_token_name)

    assert delete_config["path"] == set_config["path"]
    assert delete_config["domain"] == set_config["domain"] is None


def test_payment_settings_default_to_sandbox_and_optional(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "1")
    settings = _settings()

    assert settings.sslcommerz_is_sandbox is True
    assert settings.sslcommerz_store_id is None
    assert settings.sslcommerz_store_password is None


def test_cookie_domain_is_optional(monkeypatch):
    """Omitting COOKIE_DOMAIN must not break local startup."""
    monkeypatch.setenv("DEV_MODE", "1")
    settings = Settings(
        _env_file=None,
        DATABASE_URI="sqlite://",
        JWT_SECRET_KEY="k",
        JWT_PUBLIC_KEY="k",
        JWT_ALGORITHM="HS256",
        ACCESS_TOKEN_NAME="mpsc_access_token",
        ADMIN_SECRET="s",
    )
    assert settings.cookie_domain == ""
    assert settings.delete_cookie_config(settings.access_token_name) == {
        "key": settings.access_token_name,
        "path": "/",
        "domain": None,
    }