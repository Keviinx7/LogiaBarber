"""P1.5 input boundaries and real ASGI 422 serialization, without a database."""
import asyncio
from datetime import datetime, tzinfo
from unittest.mock import MagicMock

import httpx
import pytest
from pydantic import ValidationError

from app.api.dependencies import get_db
from app.main import app
from app.schemas.persistence import AppointmentCreate, AppointmentUpdate


def payload(**changes):
    return {
        "client_name": "María Pérez",
        "client_phone": "+34 (91) 123-4567 ext. 2",
        "service_id": 7,
        "barber_id": 11,
        "starts_at": "2035-06-03T15:30:00-05:00",
        **changes,
    }


@pytest.mark.parametrize("model", [AppointmentCreate, AppointmentUpdate])
@pytest.mark.parametrize("field,limit", [("client_name", 120), ("client_phone", 40)])
@pytest.mark.parametrize("value_kind", ["empty", "spaces", "unicode_whitespace", "too_long"])
def test_invalid_client_strings_are_rejected(model, field, limit, value_kind):
    value = {"empty": "", "spaces": "   ", "unicode_whitespace": " \t\n\u00a0 ", "too_long": "a" * (limit + 1)}[value_kind]
    with pytest.raises(ValidationError) as caught:
        model.model_validate(payload(**{field: value}))
    assert caught.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize("model", [AppointmentCreate, AppointmentUpdate])
def test_trim_exterior_preserves_content_and_accepts_exact_limits(model):
    result = model.model_validate(payload(client_name=" \tMaría  Pérez \n", client_phone=" +34 (91) 123-4567 ext. 2 "))
    assert result.client_name == "María  Pérez"
    assert result.client_phone == "+34 (91) 123-4567 ext. 2"
    boundary = model.model_validate(payload(client_name=" " + "a" * 120 + " ", client_phone=" " + "1" * 40 + " "))
    assert len(boundary.client_name) == 120
    assert len(boundary.client_phone) == 40


@pytest.mark.parametrize("model", [AppointmentCreate, AppointmentUpdate])
@pytest.mark.parametrize("field", ["service_id", "barber_id"])
@pytest.mark.parametrize("value", [0, -1])
def test_ids_must_be_positive(model, field, value):
    with pytest.raises(ValidationError) as caught:
        model.model_validate(payload(**{field: value}))
    assert caught.value.errors()[0]["loc"] == (field,)
    assert caught.value.errors()[0]["type"] == "greater_than"


class NoOffset(tzinfo):
    def utcoffset(self, dt):
        return None


@pytest.mark.parametrize("value", ["2035-06-03T15:30:00", datetime(2035, 6, 3, 15, 30), datetime(2035, 6, 3, 15, 30, tzinfo=NoOffset())])
@pytest.mark.parametrize("model,field", [(AppointmentCreate, "starts_at"), (AppointmentUpdate, "starts_at"), (AppointmentUpdate, "ends_at")])
def test_timestamps_require_an_actual_offset(model, field, value):
    with pytest.raises(ValidationError) as caught:
        model.model_validate(payload(**{field: value}))
    assert caught.value.errors()[0]["loc"] == (field,)
    assert caught.value.errors()[0]["type"] == "timezone_aware"


def test_aware_instant_precision_and_offset_are_preserved():
    timestamp = "2035-06-03T15:30:00.123456+09:00"
    assert AppointmentCreate.model_validate(payload(starts_at=timestamp)).starts_at.isoformat() == timestamp
    assert AppointmentUpdate().model_dump(exclude_unset=True) == {}


@pytest.mark.parametrize("field,value,error_type", [
    ("client_name", "   ", "string_too_short"),
    ("client_phone", "\t \n", "string_too_short"),
    ("client_name", "a" * 121, "string_too_long"),
    ("client_phone", "1" * 41, "string_too_long"),
    ("service_id", 0, "greater_than"),
    ("barber_id", -1, "greater_than"),
    ("starts_at", "2035-06-03T15:30:00", "timezone_aware"),
])
def test_post_validation_returns_structured_422_without_querying_database(monkeypatch, field, value, error_type):
    db = MagicMock()

    async def fake_db():
        return db

    monkeypatch.setitem(app.dependency_overrides, get_db, fake_db)

    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.post("/api/appointments", json=payload(**{field: value}))

    response = asyncio.run(request())
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list) and len(detail) == 1
    assert detail[0]["loc"] == ["body", field]
    assert detail[0]["type"] == error_type
    assert isinstance(detail[0]["msg"], str)
    assert "Traceback" not in response.text
    assert db.mock_calls == []
