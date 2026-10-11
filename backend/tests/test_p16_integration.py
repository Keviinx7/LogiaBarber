"""P1.6 API integration on the guarded, existing PostgreSQL test database.

Run through tests.run_p0_validation --reuse-existing. Imported P0 fixtures
check the temporary runner sentinel and physical database before any writes.
Only records created by each fixture are removed; no seed, DDL or main DB.
"""
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes import public
from app.core.config import settings
from app.models import Appointment, Barber, BlockedTime, BusinessHours, Service
from tests.test_p0_postgresql import client_factory, pg_engine  # fixtures only


@pytest.fixture
def catalog(pg_engine):
    tag = "P1.6 " + uuid4().hex
    start = (datetime.now(public.BUSINESS_TZ) + timedelta(days=14)).replace(
        hour=10, minute=0, second=0, microsecond=0,
    )
    with Session(pg_engine) as db:
        services = [Service(name=f"{tag} {minutes}", description=f"Descripción {minutes}",
                            price=Decimal("12.50"), duration_minutes=minutes, is_active=True)
                    for minutes in (20, 30, 45)]
        inactive_service = Service(name=f"{tag} inactive", price=10, duration_minutes=30, is_active=False)
        barbers = [Barber(name=f"{tag} barber {i}", is_active=i < 2) for i in range(3)]
        db.add_all([*services, inactive_service, *barbers])
        db.flush()
        ids = {s.duration_minutes: s.id for s in services}
        service_ids = [*ids.values(), inactive_service.id]
        barber_ids = [b.id for b in barbers]
        for barber in barbers:
            for day in range(7):
                db.add(BusinessHours(barber_id=barber.id, day_of_week=day,
                                     opening_time=time(10), closing_time=time(21), is_open=True))
        db.commit()
    try:
        yield SimpleNamespace(start=start, services=ids, service_ids=service_ids,
                              inactive_service=service_ids[-1], barbers=barber_ids)
    finally:
        with Session(pg_engine) as db:
            db.execute(delete(Appointment).where(Appointment.service_id.in_(service_ids)))
            db.execute(delete(BlockedTime).where(BlockedTime.barber_id.in_(barber_ids)))
            db.execute(delete(BusinessHours).where(BusinessHours.barber_id.in_(barber_ids)))
            db.execute(delete(Barber).where(Barber.id.in_(barber_ids)))
            db.execute(delete(Service).where(Service.id.in_(service_ids)))
            db.commit()


def at(catalog, hour, minute=0):
    return catalog.start.replace(hour=hour, minute=minute)


def body(catalog, **changes):
    return {"client_name": "  María  Pérez  ", "client_phone": "  +34 (91) 123-4567  ",
            "service_id": catalog.services[30], "barber_id": catalog.barbers[0],
            "starts_at": catalog.start.isoformat(), **changes}


def slots(client, catalog, *, duration=30, barber=None, day=None):
    response = client.get("/api/availability", params={
        "service_id": catalog.services[duration],
        "barber_id": catalog.barbers[0] if barber is None else barber,
        "date": (day or catalog.start.date()).isoformat(),
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["service_id"] == catalog.services[duration]
    assert result["barber_id"] == (catalog.barbers[0] if barber is None else barber)
    assert result["date"] == (day or catalog.start.date()).isoformat()
    return result["slots"]


def slot_at(result, start):
    return next(item for item in result if datetime.fromisoformat(item["starts_at"]) == start)


def count(pg_engine, catalog):
    with Session(pg_engine) as db:
        return db.scalar(select(func.count()).select_from(Appointment).where(
            Appointment.service_id.in_(catalog.service_ids)))


def test_real_catalog_active_barbers_and_public_config(pg_engine, catalog, client_factory):
    client = client_factory()
    response = client.get("/api/services")
    assert response.status_code == 200
    by_id = {item["id"]: item for item in response.json()}
    assert catalog.inactive_service not in by_id
    with Session(pg_engine) as db:
        for minutes, service_id in catalog.services.items():
            actual = db.get(Service, service_id)
            assert by_id[service_id]["name"] == actual.name
            assert by_id[service_id]["description"] == actual.description
            assert by_id[service_id]["duration_minutes"] == minutes
            assert Decimal(by_id[service_id]["price"]) == actual.price
    response = client.get("/api/barbers")
    assert response.status_code == 200
    by_id = {item["id"]: item for item in response.json()}
    assert all(barber in by_id for barber in catalog.barbers[:2])
    assert catalog.barbers[2] not in by_id
    response = client.get("/api/business-config")
    assert response.status_code == 200
    assert response.json() == {"timezone": settings.business_timezone, "opening_time": "10:00",
                               "closing_time": "21:00", "lunch_start": "14:00",
                               "lunch_end": "15:00", "working_days": list(range(7))}


@pytest.mark.parametrize("duration", [20, 30, 45])
def test_availability_uses_real_duration_lunch_and_closing(catalog, client_factory, duration):
    result = slots(client_factory(), catalog, duration=duration)
    assert result
    for item in result:
        start, end = (datetime.fromisoformat(item[key]) for key in ("starts_at", "ends_at"))
        assert start.utcoffset() is not None and end.utcoffset() is not None
        assert end - start == timedelta(minutes=duration)
        assert at(catalog, 10) <= start < end <= at(catalog, 21)
        assert not (start < at(catalog, 15) and end > at(catalog, 14))
        assert item["available"] is True
    assert slot_at(result, at(catalog, 15))["available"]
    if duration <= 30:
        assert slot_at(result, at(catalog, 13, 30))["available"]
        assert slot_at(result, at(catalog, 20, 30))["available"]
    else:
        assert all(datetime.fromisoformat(item["starts_at"]) not in
                   (at(catalog, 13, 30), at(catalog, 20, 30)) for item in result)


def test_past_date_and_today_past_equal_future(catalog, client_factory, monkeypatch):
    now = at(catalog, 10, 30)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz)

    monkeypatch.setattr(public, "datetime", Clock)
    client = client_factory()
    assert slots(client, catalog, day=now.date() - timedelta(days=1)) == []
    result = slots(client, catalog)
    assert slot_at(result, at(catalog, 10))["available"] is False
    assert slot_at(result, now)["available"] is False
    assert slot_at(result, at(catalog, 11))["available"] is True
    for start in (at(catalog, 10), now):
        response = client.post("/api/appointments", json=body(catalog, starts_at=start.isoformat()))
        assert response.status_code == 422


def test_get_selected_slot_post_and_persisted_fields(pg_engine, catalog, client_factory):
    client = client_factory()
    services_response = client.get("/api/services")
    barbers_response = client.get("/api/barbers")
    config_response = client.get("/api/business-config")
    assert services_response.status_code == barbers_response.status_code == config_response.status_code == 200
    service = next(item for item in services_response.json()
                   if item["id"] in catalog.service_ids and item["duration_minutes"] == 30)
    barber = next(item for item in barbers_response.json() if item["id"] == catalog.barbers[0])
    assert config_response.json()["timezone"] == settings.business_timezone
    availability = client.get("/api/availability", params={"service_id": service["id"],
                              "barber_id": barber["id"], "date": catalog.start.date().isoformat()})
    assert availability.status_code == 200
    selected = next(item for item in availability.json()["slots"] if item["available"])
    response = client.post("/api/appointments", json=body(catalog, service_id=service["id"],
                           barber_id=barber["id"], starts_at=selected["starts_at"]))
    assert response.status_code == 201, response.text
    record = response.json()
    with Session(pg_engine) as db:
        actual = db.get(Appointment, record["id"])
        assert actual is not None
        assert actual.service_id == catalog.services[30] == record["service_id"]
        assert actual.barber_id == catalog.barbers[0] == record["barber_id"]
        assert actual.client_name == record["client_name"] == "María  Pérez"
        assert actual.client_phone == record["client_phone"] == "+34 (91) 123-4567"
        assert actual.starts_at == datetime.fromisoformat(selected["starts_at"])
        assert actual.ends_at == datetime.fromisoformat(selected["ends_at"])
        assert actual.status == record["status"] == "pending"
        assert actual.starts_at.utcoffset() is not None
        assert actual.ends_at.utcoffset() is not None
    assert count(pg_engine, catalog) == 1
    assert slot_at(slots(client, catalog), catalog.start)["available"] is False


def test_conflict_other_barber_and_recovery_on_same_session(pg_engine, catalog, client_factory):
    with Session(pg_engine) as db:
        client = client_factory(shared_session=db)
        assert client.post("/api/appointments", json=body(catalog)).status_code == 201
        response = client.post("/api/appointments", json=body(catalog))
        assert response.status_code == 409
        assert isinstance(response.json()["detail"], str)
        assert not db.in_transaction()
        assert client.post("/api/appointments", json=body(catalog, barber_id=catalog.barbers[1])).status_code == 201
        assert client.post("/api/appointments", json=body(catalog, starts_at=at(catalog, 10, 30).isoformat())).status_code == 201
    assert count(pg_engine, catalog) == 3


@pytest.mark.parametrize("status,blocked", [("pending", True), ("confirmed", True),
                                            ("cancelled", False), ("completed", False), ("no_show", False)])
def test_persisted_states_control_availability_and_post(pg_engine, catalog, client_factory, status, blocked):
    client = client_factory()
    response = client.post("/api/appointments", json=body(catalog))
    assert response.status_code == 201
    with Session(pg_engine) as db:
        db.get(Appointment, response.json()["id"]).status = status
        db.commit()
    assert slot_at(slots(client, catalog), catalog.start)["available"] is not blocked
    assert slot_at(slots(client, catalog, barber=catalog.barbers[1]), catalog.start)["available"] is True
    second = client.post("/api/appointments", json=body(catalog))
    assert second.status_code == (409 if blocked else 201)
    assert count(pg_engine, catalog) == (1 if blocked else 2)


def test_cancellation_releases_previously_unavailable_slot(pg_engine, catalog, client_factory):
    client = client_factory()
    response = client.post("/api/appointments", json=body(catalog))
    assert response.status_code == 201
    assert slot_at(slots(client, catalog), catalog.start)["available"] is False
    # No cancellation API is added by P1.6: change only the fixture-owned row.
    with Session(pg_engine) as db:
        db.get(Appointment, response.json()["id"]).status = "cancelled"
        db.commit()
    assert slot_at(slots(client, catalog), catalog.start)["available"] is True
    assert client.post("/api/appointments", json=body(catalog)).status_code == 201


@pytest.mark.parametrize("hour,minute,duration,expected", [
    (9, 30, 30, 422), (10, 0, 30, 201), (13, 30, 30, 201),
    (13, 30, 45, 422), (14, 0, 30, 422), (14, 30, 45, 422),
    (15, 0, 30, 201), (20, 30, 30, 201), (20, 30, 45, 422), (21, 0, 20, 422),
])
def test_post_business_boundaries(pg_engine, catalog, client_factory, hour, minute, duration, expected):
    response = client_factory().post("/api/appointments", json=body(
        catalog, service_id=catalog.services[duration], starts_at=at(catalog, hour, minute).isoformat()))
    assert response.status_code == expected, response.text
    assert count(pg_engine, catalog) == (1 if expected == 201 else 0)
    if expected == 201:
        assert datetime.fromisoformat(response.json()["ends_at"]) == at(catalog, hour, minute) + timedelta(minutes=duration)


def test_expired_post_and_offset_instant_precision(pg_engine, catalog, client_factory):
    client = client_factory()
    expired = datetime.now(public.BUSINESS_TZ) - timedelta(days=1)
    assert client.post("/api/appointments", json=body(catalog, starts_at=expired.isoformat())).status_code == 422
    instant = catalog.start.replace(microsecond=123456).astimezone(timezone(timedelta(hours=9)))
    response = client.post("/api/appointments", json=body(catalog, starts_at=instant.isoformat()))
    assert response.status_code == 201
    returned = datetime.fromisoformat(response.json()["starts_at"])
    assert returned == instant and returned.microsecond == 123456
    with Session(pg_engine) as db:
        actual = db.get(Appointment, response.json()["id"])
        assert actual.starts_at == instant and actual.starts_at.utcoffset() is not None
    assert count(pg_engine, catalog) == 1


@pytest.mark.parametrize("field,value", [
    ("client_name", "   "), ("client_name", "a" * 121),
    ("client_phone", " \t "), ("client_phone", "1" * 41),
    ("service_id", 0), ("barber_id", -1), ("starts_at", "2035-06-03T10:00:00"),
])
def test_invalid_body_422_does_not_persist(pg_engine, catalog, client_factory, field, value):
    response = client_factory().post("/api/appointments", json=body(catalog, **{field: value}))
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["loc"] == ["body", field]
    assert isinstance(detail[0]["msg"], str)
    assert count(pg_engine, catalog) == 0


@pytest.mark.parametrize("field", ["service_id", "barber_id"])
def test_inactive_ids_are_not_bookable(pg_engine, catalog, client_factory, field):
    value = catalog.inactive_service if field == "service_id" else catalog.barbers[2]
    response = client_factory().post("/api/appointments", json=body(catalog, **{field: value}))
    assert response.status_code == 404
    assert count(pg_engine, catalog) == 0


def test_specific_barber_block_remains_independent(pg_engine, catalog, client_factory):
    with Session(pg_engine) as db:
        db.add(BlockedTime(barber_id=catalog.barbers[0], starts_at=catalog.start,
                           ends_at=at(catalog, 11), reason="P1.6 fixture exception"))
        db.commit()
    client = client_factory()
    assert slot_at(slots(client, catalog), catalog.start)["available"] is False
    assert slot_at(slots(client, catalog, barber=catalog.barbers[1]), catalog.start)["available"] is True
    assert client.post("/api/appointments", json=body(catalog)).status_code == 409
    assert client.post("/api/appointments", json=body(catalog, barber_id=catalog.barbers[1])).status_code == 201


def test_actual_foreign_key_violation_remains_500_and_rolls_back(pg_engine, catalog, client_factory):
    errors = []

    class InvalidForeignKeySession(Session):
        def commit(self):
            # Controlled fault injection; the 23503 itself comes from PostgreSQL.
            for row in self.new:
                if isinstance(row, Appointment):
                    row.service_id = -1
            try:
                super().commit()
            except IntegrityError as error:
                errors.append(error.orig.sqlstate)
                raise

    with InvalidForeignKeySession(pg_engine) as db:
        client = client_factory(shared_session=db)
        response = client.post("/api/appointments", json=body(catalog))
        assert errors == ["23503"]
        assert response.status_code == 500
        assert response.text == "Internal Server Error"
        assert not db.in_transaction()
    assert count(pg_engine, catalog) == 0
