import os
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_uri: str = Field(..., validation_alias="DATABASE_URI")
    jwt_private_key: str = Field(..., validation_alias="JWT_SECRET_KEY")
    jwt_public_key: str = Field(..., validation_alias="JWT_PUBLIC_KEY")
    jwt_algorithm: str = Field(..., validation_alias="JWT_ALGORITHM")
    access_token_name: str = Field(..., validation_alias="ACCESS_TOKEN_NAME")

    def access_token_config(self, access_token: str, max_age: int) -> dict[str, Any]:
        dev_mode = os.getenv("DEV_MODE")

        return dict(
            key=self.access_token_name,
            value=access_token,
            httponly=True,
            path="/",
            max_age=max_age,
            samesite="none",
            secure=True,
            domain="mpsc50years.docufybd.com" if not dev_mode else None,
        )

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()  # type: ignore[assignment]
