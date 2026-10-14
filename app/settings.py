from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_uri: str = Field(..., validation_alias="DATABASE_URI")
    jwt_private_key: str = Field(..., validation_alias="JWT_SECRET_KEY")
    jwt_public_key: str = Field(..., validation_alias="JWT_PUBLIC_KEY")
    jwt_algorithm: str = Field(..., validation_alias="JWT_ALGORITHM")
    access_token_name: str = Field(..., validation_alias="ACCESS_TOKEN_NAME")
    admin_access_token_name: str = Field(
        default=..., validation_alias="ADMIN_ACCESS_TOKEN_NAME"
    )

    domain: str = Field(default=..., validation_alias="COOKIE_DOMAIN")
    frontend_url: str = Field(
        default="http://localhost:3000", validation_alias="FRONTEND_URL"
    )
    sslcommerz_store_id: str = Field(
        default=..., validation_alias="SSLCOMMERZ_STORE_ID"
    )
    sslcommerz_store_password: str = Field(
        default=..., validation_alias="SSLCOMMERZ_STORE_PASSWORD"
    )
    sslcommerz_is_sandbox: bool = Field(
        default=True, validation_alias="SSLCOMMERZ_IS_SANDBOX"
    )
    # for sslcommerz
    api_url: str = Field(default="http://localhost:8000", validation_alias="API_URL")

    event_fee_bdt: int = 1500
    sponsor_offer_limit: int = 3
    openmic_entry_limit: int = 2
    openmic_max_duration_minutes: int = 10

    dev_mode: bool = Field(default=False, validation_alias="DEV_MODE")

    def _cookie_config(
        self, key: str, value: str, max_age: int | None
    ) -> dict[str, Any]:
        return {
            "key": key,
            "value": value,
            "httponly": True,
            "path": "/",
            "max_age": max_age,
            "samesite": "lax" if self.dev_mode else "none",
            "secure": False,
            "domain": None if self.dev_mode else self.domain,
        }

    def access_token_config(self, access_token: str, max_age: int) -> dict[str, Any]:
        return self._cookie_config(self.access_token_name, access_token, max_age)

    def admin_access_token_config(
        self, admin_access_token: str, max_age: int
    ) -> dict[str, Any]:
        return self._cookie_config(
            self.admin_access_token_name, admin_access_token, max_age
        )

    def delete_cookie_config(self, key: str) -> dict[str, Any]:
        return {
            "key": key,
            "path": "/",
            "domain": None if self.dev_mode else self.domain,
        }


settings = Settings()  # type: ignore[assignment]
