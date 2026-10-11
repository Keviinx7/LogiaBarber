"""P1.3 availability with a controlled aware clock; no database connection."""
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.api.routes import public
from app.models import Appointment, BlockedTime
from app.schemas import AppointmentCreate, AvailabilityResponse

DAY = date(2026, 10, 5)


def instant(day=DAY, hour=10, minute=0):
    return datetime.combine(day, time(hour, minute), public.BUSINESS_TZ)


@pytest.fixture
def clock(monkeypatch):
    class Clock(datetime):
        value = instant(hour=11)

        @classmethod
        def now(cls, tz=None):
            assert tz is public.BUSINESS_TZ
            return cls.value.astimezone(tz)

    monkeypatch.setattr(public, "datetime", Clock)
    return Clock


def database(*, duration=30, appointments=(), blocked=()):
    db = MagicMock()
    db.scalar.side_effect = [
        SimpleNamespace(duration_minutes=duration), SimpleNamespace(id=11),
        SimpleNamespace(is_open=True, opening_time=time(10), closing_time=time(21)),
    ]

    def scalars(statement):
        compiled = statement.compile(dialect=postgresql.dialect())
        params, sql = compiled.params, str(compiled)
        entity = statement.column_descriptions[0]["entity"]
        if entity is Appointment:
            # Check the actual SQL predicates as well as the resulting intervals.
            assert "appointments.barber_id =" in sql
            assert "appointments.status IN" in sql
            assert tuple(params["status_1"]) == ("pending", "confirmed")
            assert "appointments.starts_at <" in sql and "appointments.ends_at >" in sql
            candidates = [a for a in appointments if a.status in params["status_1"]]
        else:
            assert entity is BlockedTime
            assert "blocked_times.barber_id =" in sql
            assert "blocked_times.starts_at <" in sql and "blocked_times.ends_at >" in sql
            candidates = blocked
        rows = [a for a in candidates if a.barber_id == params["barber_id_1"]
                and a.starts_at < params["starts_at_1"] and a.ends_at > params["ends_at_1"]]
        return SimpleNamespace(all=lambda: rows)

    db.scalars.side_effect = scalars
    return db


def availability(db, day=DAY, barber=11):
    # Validate the very response model used by GET, including empty past dates.
    return AvailabilityResponse.model_validate(public.availability(7, barber, day, db))


def test_yesterday_returns_typed_empty_response(clock):
    db = database()
    result = availability(db, DAY - timedelta(days=1))
    assert result.model_dump(mode="json") == {
        "date": "2026-10-04", "service_id": 7, "barber_id": 11, "slots": [],
    }
    assert db.scalar.call_count == 2  # no schedule/interval queries for the past
    db.scalars.assert_not_called()


def test_today_excludes_past_and_exact_now_but_keeps_future(clock):
    result = availability(database())
    by_time = {slot.starts_at.time(): slot for slot in result.slots}
    assert by_time[time(10)].available is False
    assert by_time[time(10, 30)].available is False
    assert by_time[time(11)].available is False
    assert by_time[time(11, 30)].available is True
    assert all(slot.starts_at > clock.value for slot in result.slots if slot.available)
    assert all(slot.starts_at.tzinfo is not None for slot in result.slots)


def test_future_date_still_offers_slots(clock):
    result = availability(database(), DAY + timedelta(days=1))
    assert len(result.slots) == 20  # P1.4 excludes the two lunch candidates
    assert all(slot.available for slot in result.slots)


def test_business_day_does_not_advance_at_utc_midnight(clock):
    clock.value = datetime.fromisoformat("2026-10-06T00:00:00+00:00")
    result = availability(database())  # Guayaquil is still October 5, 19:00
    assert result.slots
    assert all(slot.starts_at > clock.value for slot in result.slots if slot.available)
    assert next(s for s in result.slots if s.starts_at.time() == time(19)).available is False
    assert next(s for s in result.slots if s.starts_at.time() == time(19, 30)).available is True


@pytest.mark.parametrize("duration,last_start", [(30, time(20, 30)), (45, time(20)), (90, time(19, 30))])
def test_duration_respects_existing_closing_time(clock, duration, last_start):
    day = DAY + timedelta(days=1)
    result = availability(database(duration=duration), day)
    assert result.slots[-1].starts_at.time() == last_start
    assert all(s.ends_at <= instant(day, 21) for s in result.slots)
    assert all(s.ends_at - s.starts_at == timedelta(minutes=duration) for s in result.slots)


@pytest.mark.parametrize("status,blocks", [("pending", True), ("confirmed", True),
                                          ("cancelled", False), ("completed", False), ("no_show", False)])
def test_appointment_status_filters(clock, status, blocks):
    clock.value = instant(hour=9)
    appointment = SimpleNamespace(barber_id=11, status=status, starts_at=instant(), ends_at=instant(hour=11))
    result = availability(database(appointments=[appointment]))
    assert result.slots[0].available is not blocks
    assert result.slots[1].available is not blocks
    assert result.slots[2].available is True  # adjacent intervals remain valid


@pytest.mark.parametrize("barber,available", [(11, False), (12, True)])
def test_barbers_keep_independent_appointment_and_blocked_agendas(clock, barber, available):
    clock.value = instant(hour=9)
    appointment = SimpleNamespace(barber_id=11, status="pending", starts_at=instant(), ends_at=instant(hour=11))
    block = SimpleNamespace(barber_id=11, starts_at=instant(hour=11), ends_at=instant(hour=12))
    result = availability(database(appointments=[appointment], blocked=[block]), barber=barber)
    assert all(s.available is available for s in result.slots[:4])
    assert result.slots[4].available is True


@pytest.mark.parametrize("elapsed", [0, 1])
def test_post_still_rejects_slot_that_expired_after_get(clock, elapsed):
    clock.value = instant(hour=9)
    slot = availability(database()).slots[0]
    assert slot.available
    clock.value = slot.starts_at + timedelta(seconds=elapsed)
    payload = AppointmentCreate(client_name="P1.3", client_phone="099", service_id=7, barber_id=11, starts_at=slot.starts_at)
    db = database()
    with pytest.raises(HTTPException) as caught:
        public.create_appointment(payload, db)
    assert caught.value.status_code == 422
    db.rollback.assert_called_once_with()
    db.commit.assert_not_called()
