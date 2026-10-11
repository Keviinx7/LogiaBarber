"""P1.4 recurring rules and GET/POST agreement, with no database connection."""
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.routes import public
from app.models import Appointment, Barber, BlockedTime, BusinessHours, Service
from app.schemas import AppointmentCreate, AvailabilityResponse
from app.services import business_rules as rules

DAY = date(2030, 6, 2)  # Sunday, deliberately beyond the old seed's date window.


def at(hour, minute=0, day=DAY):
    return datetime.combine(day, time(hour, minute), public.BUSINESS_TZ)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is public.BUSINESS_TZ
            return datetime(2026, 1, 1, tzinfo=tz)
    monkeypatch.setattr(public, "datetime", Clock)


def route_db(duration=30, *, opening=time(10), closing=time(21), is_open=True, blocks=()):
    db = MagicMock()

    def block_rows(statement):
        params = statement.compile().params
        sql = str(statement)
        assert "blocked_times.barber_id =" in sql
        assert "blocked_times.starts_at <" in sql and "blocked_times.ends_at >" in sql
        return [b for b in blocks if b.barber_id == params['barber_id_1']
                and b.starts_at < params['starts_at_1'] and b.ends_at > params['ends_at_1']]

    def scalar(statement):
        entity = statement.column_descriptions[0]['entity']
        if entity is Service:
            return SimpleNamespace(duration_minutes=duration)
        if entity is Barber:
            return SimpleNamespace(id=statement.compile().params['id_1'])
        if entity is BusinessHours:
            return SimpleNamespace(opening_time=opening, closing_time=closing, is_open=is_open)
        assert entity is BlockedTime
        return next(iter(block_rows(statement)), None)

    def scalars(statement):
        entity = statement.column_descriptions[0]['entity']
        if entity is Appointment:
            rows = []
        else:
            assert entity is BlockedTime
            rows = block_rows(statement)
        return SimpleNamespace(all=lambda: rows)

    db.scalar.side_effect, db.scalars.side_effect = scalar, scalars
    return db


def get_slots(db, day=DAY, barber=11):
    result = AvailabilityResponse.model_validate(public.availability(7, barber, day, db))
    return result.slots


def post(db, start, barber=11):
    return public.create_appointment(AppointmentCreate(
        client_name='P1.4', client_phone='099', service_id=7, barber_id=barber, starts_at=start,
    ), db)


# Explicit acceptance matrix: the same fixtures exercise pure rules, GET and POST.
@pytest.mark.parametrize('hour,minute,duration,allowed', [
    (10, 0, 30, True), (9, 30, 30, False),
    (13, 30, 30, True), (13, 30, 60, False),
    (14, 0, 30, False), (14, 30, 30, False), (14, 30, 60, False),
    (15, 0, 30, True), (20, 30, 30, True), (20, 30, 45, False),
    (13, 30, 20, True), (13, 30, 45, False), (15, 0, 45, True),
    (20, 30, 20, True),
])
def test_same_rules_in_pure_function_availability_and_post(hour, minute, duration, allowed):
    start = at(hour, minute)
    end = start + timedelta(minutes=duration)
    window = rules.business_window(DAY, public.BUSINESS_TZ)
    assert rules.interval_allowed(start, end, window, public.BUSINESS_TZ) is allowed
    slots = get_slots(route_db(duration))
    matches = [s for s in slots if s.starts_at == start]
    assert bool(matches) is allowed
    if allowed:
        assert matches[0].available and matches[0].ends_at == end
        db = route_db(duration)
        appointment = post(db, start)
        assert appointment.ends_at == end
        db.commit.assert_called_once_with()
    else:
        db = route_db(duration)
        with pytest.raises(HTTPException) as caught:
            post(db, start)
        assert caught.value.status_code == 422
        db.commit.assert_not_called()
        db.rollback.assert_called_once_with()


def test_sunday_has_normal_hours_and_lunch():
    assert DAY.weekday() == 6
    assert rules.business_window(DAY, public.BUSINESS_TZ) == (at(10), at(21))
    slots = get_slots(route_db())
    assert slots[0].starts_at == at(10)
    assert slots[-1].ends_at == at(21)
    assert len(slots) == 20
    assert all(not rules.overlaps_lunch(s.starts_at, s.ends_at, public.BUSINESS_TZ) for s in slots)


@pytest.mark.parametrize('day', [date(2027, 2, 1), date(2026, 12, 31), date(2027, 1, 1), date(2035, 12, 31), date(2036, 1, 1)])
def test_recurring_rule_has_no_year_or_seed_window(day):
    slots = get_slots(route_db(), day)
    assert slots and all(s.available for s in slots)
    assert all(s.starts_at.date() == day and s.starts_at.utcoffset() is not None for s in slots)
    assert not any(s.starts_at.time() in (time(14), time(14, 30)) for s in slots)
    with pytest.raises(HTTPException) as caught:
        post(route_db(60), at(13, 30, day))
    assert caught.value.status_code == 422


@pytest.mark.parametrize('duration', [20, 30, 45])
def test_actual_service_duration_for_every_candidate(duration):
    for s in get_slots(route_db(duration)):
        assert s.ends_at - s.starts_at == timedelta(minutes=duration)
        assert s.starts_at >= at(10) and s.ends_at <= at(21)
        assert not (s.starts_at < at(15) and s.ends_at > at(14))


def test_custom_barber_hours_remain_restrictive():
    slots = get_slots(route_db(opening=time(11), closing=time(17)))
    assert slots[0].starts_at == at(11) and slots[-1].ends_at == at(17)
    with pytest.raises(HTTPException):
        post(route_db(opening=time(11), closing=time(17)), at(10))
    assert get_slots(route_db(is_open=False)) == []
    with pytest.raises(HTTPException):
        post(route_db(is_open=False), at(10))


def test_wider_configured_hours_cannot_bypass_business_limits():
    slots = get_slots(route_db(opening=time(8), closing=time(23)))
    assert slots[0].starts_at == at(10) and slots[-1].ends_at == at(21)
    for start in [at(9), at(21)]:
        with pytest.raises(HTTPException) as caught:
            post(route_db(opening=time(8), closing=time(23)), start)
        assert caught.value.status_code == 422


@pytest.mark.parametrize('barber,available', [(11, False), (12, True)])
def test_specific_block_still_applies_only_to_its_barber(barber, available):
    block = SimpleNamespace(barber_id=11, starts_at=at(16), ends_at=at(17))
    slots = get_slots(route_db(blocks=[block]), barber=barber)
    assert next(s for s in slots if s.starts_at == at(16)).available is available
    assert not any(s.starts_at == at(14) for s in slots)
    db = route_db(blocks=[block])
    if available:
        assert post(db, at(16), barber).barber_id == barber
    else:
        with pytest.raises(HTTPException) as caught:
            post(db, at(16), barber)
        assert caught.value.status_code == 409


def test_historical_lunch_block_does_not_break_adjacent_boundaries():
    block = SimpleNamespace(barber_id=11, starts_at=at(14), ends_at=at(15))
    slots = get_slots(route_db(blocks=[block]))
    assert next(s for s in slots if s.starts_at == at(13, 30)).available
    assert next(s for s in slots if s.starts_at == at(15)).available
    assert post(route_db(blocks=[block]), at(15)).starts_at == at(15)


def test_utc_instants_use_business_local_lunch():
    with pytest.raises(HTTPException) as caught:
        post(route_db(60), at(13, 30).astimezone(timezone.utc))
    assert caught.value.status_code == 422
    assert post(route_db(), at(15).astimezone(timezone.utc)).starts_at == at(15)


def test_helpers_return_aware_instants_and_reject_naive_input():
    window = rules.business_window(DAY, public.BUSINESS_TZ)
    assert all(t.utcoffset() is not None for t in (*window, *rules.lunch_window(DAY, public.BUSINESS_TZ)))
    with pytest.raises(ValueError, match='timezone-aware'):
        rules.interval_allowed(at(10).replace(tzinfo=None), at(11), window, public.BUSINESS_TZ)
    with pytest.raises(ValueError, match='timezone-aware'):
        rules.overlaps_lunch(at(14), at(15).replace(tzinfo=None), public.BUSINESS_TZ)
    assert not rules.interval_allowed(at(15), at(15), window, public.BUSINESS_TZ)
    assert not rules.interval_allowed(at(15), at(10), window, public.BUSINESS_TZ)
