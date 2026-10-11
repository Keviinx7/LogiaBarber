"""Execute seed only against an in-memory fixture, never a database."""
from contextlib import contextmanager
from datetime import time

import pytest

from app.models import Barber, BlockedTime, BusinessHours, Service
from app.scripts import seed as seed_module
from app.services.business_rules import CLOSING_TIME, OPENING_TIME, WORKING_DAYS


class SeedFixture:
    def __init__(self):
        self.rows = []

    def scalar(self, statement):
        entity = statement.column_descriptions[0]['entity']
        assert entity in (Service, Barber, BusinessHours)
        params = statement.compile().params
        return next((row for row in self.rows if isinstance(row, entity) and all(
            getattr(row, key.rsplit('_', 1)[0]) == value for key, value in params.items()
        )), None)

    def add(self, row):
        assert isinstance(row, (Service, Barber, BusinessHours))
        row.id = len(self.rows) + 1
        self.rows.append(row)

    def flush(self):
        pass

    @contextmanager
    def begin(self):
        yield self


@pytest.fixture
def db(monkeypatch):
    fixture = SeedFixture()
    monkeypatch.setattr(seed_module, 'SessionLocal', fixture)
    return fixture


def test_seed_keeps_initial_catalog_barbers_and_seven_days_without_daily_blocks(db):
    seed_module.seed()
    services = [r for r in db.rows if isinstance(r, Service)]
    barbers = [r for r in db.rows if isinstance(r, Barber)]
    hours = [r for r in db.rows if isinstance(r, BusinessHours)]
    assert [(s.name, s.duration_minutes, str(s.price)) for s in services] == [
        ('Corte clásico', 30, '5.00'), ('Corte + barba', 45, '7.00'), ('Barba', 20, '3.00'),
    ]
    assert all(s.description and s.is_active for s in services)
    assert len(barbers) == 2 and len(hours) == 14 and len(db.rows) == 19
    for barber in barbers:
        assert {h.day_of_week for h in hours if h.barber_id == barber.id} == set(WORKING_DAYS)
    assert all(h.is_open and h.opening_time == OPENING_TIME and h.closing_time == CLOSING_TIME for h in hours)
    assert not any(isinstance(r, BlockedTime) for r in db.rows)


def test_repeated_seed_is_idempotent_and_preserves_custom_hours_and_old_blocks(db):
    seed_module.seed()
    hours = next(r for r in db.rows if isinstance(r, BusinessHours))
    hours.opening_time, hours.closing_time, hours.is_open = time(11), time(17), False
    historical = BlockedTime(barber_id=4, reason='Almuerzo histórico')
    db.rows.append(historical)
    original = list(db.rows)
    seed_module.seed()
    seed_module.seed()
    assert db.rows == original
    assert hours.opening_time == time(11) and hours.closing_time == time(17) and not hours.is_open
    assert historical in db.rows


def test_seed_does_not_depend_on_calendar_year(db, monkeypatch):
    class ForbiddenClock:
        def __new__(cls, *args, **kwargs):
            raise AssertionError('Seed must not construct dated lunch intervals')
    monkeypatch.setattr(seed_module, 'datetime', ForbiddenClock, raising=False)
    seed_module.seed()
    assert len(db.rows) == 19
