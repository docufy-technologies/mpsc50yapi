from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_uri: str = Field(..., validation_alias="DATABASE_URI")
    jwt_private_key: str = Field(..., validation_alias="JWT_SECRET_KEY")
    jwt_public_key: str = Field(..., validation_alias="JWT_PUBLIC_KEY")
    jwt_algorithm: str = Field(..., validation_alias="JWT_ALGORITHM")
    access_token_name: str = Field(..., validation_alias="ACCESS_TOKEN_NAME")
    admin_secret: str = Field(..., validation_alias="ADMIN_SECRET")
    # Kept separate from the alumna cookie so the two sessions cannot be confused.
    admin_token_name: str = Field(
        default="mpsc_admin_token", validation_alias="ADMIN_TOKEN_NAME"
    )

    cookie_domain: str = Field(default="", validation_alias="COOKIE_DOMAIN")
    frontend_url: str = Field(
        default="http://localhost:3000", validation_alias="FRONTEND_URL"
    )
    sslcommerz_store_id: str | None = Field(
        default=None, validation_alias="SSLCOMMERZ_STORE_ID"
    )
    sslcommerz_store_password: str | None = Field(
        default=None, validation_alias="SSLCOMMERZ_STORE_PASSWORD"
    )
    sslcommerz_is_sandbox: bool = Field(
        default=True, validation_alias="SSLCOMMERZ_IS_SANDBOX"
    )
    # Must be the API, not the frontend: the browser lands here to validate.
    api_url: str = Field(
        default="http://localhost:8000", validation_alias="API_URL"
    )
    event_fee_bdt: int = Field(default=1500, validation_alias="EVENT_FEE_BDT")
    sponsor_offer_limit: int = Field(default=3, validation_alias="SPONSOR_OFFER_LIMIT", gt=0)
    openmic_entry_limit: int = Field(default=2, validation_alias="OPENMIC_ENTRY_LIMIT", gt=0)
    openmic_max_duration_minutes: int = Field(
        default=10, validation_alias="OPENMIC_MAX_DURATION_MINUTES", gt=0
    )
    # Must be a real field, not an os.getenv lookup: pydantic-settings loads
    # .env into this object, not into os.environ, so an os.getenv check would
    # silently ignore the value in .env.
    dev_mode: bool = Field(default=False, validation_alias="DEV_MODE")

    @field_validator("dev_mode", mode="before")
    @classmethod
    def _parse_dev_mode(cls, value: object) -> object:
        """Accept the usual spellings and treat an empty value as False.

        Without this, `DEV_MODE=` (an empty line in .env) raises a validation
        error on startup, since bool("") is not a valid bool for pydantic.
        """
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"", "0", "false", "no", "off"}:
                return False
        return value

    def _cookie_config(
        self, key: str, value: str, max_age: int | None
    ) -> dict[str, Any]:
        """Build set_cookie kwargs for one cookie.

        In dev we must not force Secure/SameSite=None, otherwise the browser
        silently drops the cookie over plain http://localhost.
        """
        if self.dev_mode:
            return dict(
                key=key,
                value=value,
                httponly=True,
                path="/",
                max_age=max_age,
                samesite="lax",
                secure=False,
                domain=None,
            )

        return dict(
            key=key,
            value=value,
            httponly=True,
            path="/",
            max_age=max_age,
            samesite="none",
            secure=True,
            domain=self.cookie_domain,
        )

    def access_token_config(self, access_token: str, max_age: int) -> dict[str, Any]:
        return self._cookie_config(self.access_token_name, access_token, max_age)

    def admin_token_config(self, admin_token: str, max_age: int) -> dict[str, Any]:
        return self._cookie_config(self.admin_token_name, admin_token, max_age)

    def delete_cookie_config(self, key: str) -> dict[str, Any]:
        """delete_cookie requires the exact same path/domain as set_cookie,
        otherwise the browser keeps the original cookie."""
        if self.dev_mode:
            return dict(key=key, path="/", domain=None)
        return dict(key=key, path="/", domain=self.cookie_domain)

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()  # type: ignore[assignment]
