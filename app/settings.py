from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_uri: str = Field(..., validation_alias="DATABASE_URI")


settings = Settings()  # type: ignore[assignment]
