"""P1.2 public configuration checks: no database connections."""
import asyncio

import httpx
import pytest
from pydantic import ValidationError

from app.api.dependencies import get_db
from app.api.routes import public
from app.core.config import Settings
from app.main import app


@pytest.mark.parametrize("timezone", ["America/Guayaquil", "Europe/Madrid", "Asia/Tokyo"])
def test_public_config_uses_environment_and_exposes_only_public_fields(monkeypatch, timezone):
    monkeypatch.setenv("BUSINESS_TIMEZONE", timezone)
    config = Settings(_env_file=None, database_url="postgresql+psycopg://offline/offline")
    monkeypatch.setattr(public, "settings", config)

    def refuse_database():
        pytest.fail("business-config must not access the database")

    monkeypatch.setitem(app.dependency_overrides, get_db, refuse_database)
    async def request_config():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.get("/api/business-config")

    response = asyncio.run(request_config())
    assert response.status_code == 200
    assert response.json() == {
        "timezone": timezone, "opening_time": "10:00", "closing_time": "21:00",
        "lunch_start": "14:00", "lunch_end": "15:00", "working_days": list(range(7)),
    }


@pytest.mark.parametrize("timezone", ["Invalid/Timezone", "", "-05:00", "/etc/passwd", "../UTC"])
def test_invalid_business_timezone_fails_settings_validation(monkeypatch, timezone):
    monkeypatch.setenv("BUSINESS_TIMEZONE", timezone)
    with pytest.raises(ValidationError, match="BUSINESS_TIMEZONE debe ser una zona IANA válida") as caught:
        Settings(_env_file=None, database_url="postgresql+psycopg://offline/offline")
    assert caught.value.errors()[0]["loc"] == ("business_timezone",)
