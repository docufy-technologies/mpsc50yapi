from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DeadlineKey = Literal["registration", "stall", "sponsor", "subcommittee", "openmic"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_uri: str = Field(..., validation_alias="DATABASE_URI")
    jwt_private_key: str = Field(..., validation_alias="JWT_PRIVATE_KEY")
    jwt_public_key: str = Field(..., validation_alias="JWT_PUBLIC_KEY")
    jwt_algorithm: str = Field(..., validation_alias="JWT_ALGORITHM")
    alum_access_token: str = Field(..., validation_alias="ALUM_ACCESS_TOKEN_NAME")
    admin_access_token: str = Field(
        default=..., validation_alias="ADMIN_ACCESS_TOKEN_NAME"
    )
    alum_refresh_token: str = Field(
        default=..., validation_alias="ALUM_REFRESH_TOKEN_NAME"
    )
    admin_refresh_token: str = Field(
        default=..., validation_alias="ADMIN_REFRESH_TOKEN_NAME"
    )

    # Hardcoded token lifetimes (seconds).
    access_token_ttl_seconds: int = 15 * 60
    admin_refresh_token_ttl_seconds: int = 30 * 60
    alum_refresh_token_ttl_seconds: int = 60 * 60 * 24 * 7

    domain: str = Field(default=..., validation_alias="COOKIE_DOMAIN")
    subcommittee_names: set[str] = {
        "Registration",
        "Food and Hospitality",
        "Cultural Program",
        "Publicity",
        "Logistics",
        "Finance",
    }
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
    app_url: str = Field(default="http://localhost:8000", validation_alias="API_URL")

    event_fee_bdt: int = 3000
    sponsor_offer_limit: int = 3
    openmic_entry_limit: int = 2
    openmic_max_duration_minutes: int = 10

    # TODO: Make it editable via connected CRM
    event_deadlines: dict[DeadlineKey, datetime] = {
        "registration": datetime(2026, 11, 11, 23, 59, 59, tzinfo=UTC)
        + timedelta(hours=6),
        "stall": datetime(2026, 11, 10, 23, 59, 59, tzinfo=UTC) + timedelta(hours=6),
        "sponsor": datetime(2026, 11, 10, 23, 59, 59, tzinfo=UTC) + timedelta(hours=6),
        "subcommittee": datetime(2026, 11, 10, 23, 59, 59, tzinfo=UTC)
        + timedelta(hours=6),
        "openmic": datetime(2026, 11, 10, 23, 59, 59, tzinfo=UTC) + timedelta(hours=6),
    }

    media_dir: Path = Path("media")

    @property
    def alumni_pfp_dir(self) -> Path:
        # reasoning[rakibulhasanratul]: made a property jut to add a docstring
        "Directory for storing alumni profile pictures (relative to alumni/)."
        return Path("alumni") / "profile-pictures"

    @property
    def alumni_pfp_path(self) -> Path:
        "Full path to the directory for storing alumni profile pictures (relative to media/)."
        return self.media_dir / self.alumni_pfp_dir

    def form_alumni_pfp_file_path(self, filename: str) -> Path:
        self.alumni_pfp_path.mkdir(parents=True, exist_ok=True)
        return self.media_dir / self.alumni_pfp_dir / filename

    max_allowed_dimension: int = 1000
    allowed_image_mime_types: set[str] = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/bmp",
        "image/tiff",
    }
    max_allowed_image_size_bytes: int = 100 * 1024  # 100kb
    image_upload_size_cap_bytes: int = 5 * 1024 * 1024  # 5MB

    dev_mode: bool = Field(default=False, validation_alias="DEV_MODE")

    @model_validator(mode="after")
    def apply_dev_mode_urls(self) -> "Settings":
        if self.dev_mode:
            self.frontend_url = "http://localhost:3000"
            self.app_url = "http://localhost:8000"
        return self

    def _cookie_param(
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

    def access_token_cookie_param(
        self, access_token: str, entity: Literal["alum", "admin"]
    ) -> dict[str, Any]:
        key = self.alum_access_token if entity == "alum" else self.admin_access_token
        return self._cookie_param(key, access_token, self.access_token_ttl_seconds)

    def refresh_token_cookie_param(
        self, refresh_token: str, entity: Literal["alum", "admin"]
    ) -> dict[str, Any]:
        key = self.alum_refresh_token if entity == "alum" else self.admin_refresh_token
        max_age = (
            self.alum_refresh_token_ttl_seconds
            if entity == "alum"
            else self.admin_refresh_token_ttl_seconds
        )
        return self._cookie_param(key, refresh_token, max_age)

    def _cookie_deletion_param(self, key: str) -> dict[str, Any]:
        return {
            "key": key,
            "path": "/",
            "domain": None if self.dev_mode else self.domain,
        }

    def access_token_cookie_deletion_param(
        self, entity: Literal["alum", "admin"]
    ) -> dict[str, Any]:
        key = self.alum_access_token if entity == "alum" else self.admin_access_token
        return self._cookie_deletion_param(key)

    def refresh_token_cookie_deletion_param(
        self, entity: Literal["alum", "admin"]
    ) -> dict[str, Any]:
        key = self.alum_refresh_token if entity == "alum" else self.admin_refresh_token
        return self._cookie_deletion_param(key)


settings = Settings()  # type: ignore[assignment]
