from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Sistema de Gestión para Logia Barber"
    database_url: str
    business_timezone: str = "America/Guayaquil"

    @field_validator("business_timezone")
    @classmethod
    def validate_business_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("BUSINESS_TIMEZONE debe ser una zona IANA válida") from error
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
    )


settings = Settings()
