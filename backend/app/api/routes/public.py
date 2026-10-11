from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.config import settings
from app.models import Appointment, Barber, BlockedTime, BusinessHours, Service
from app.schemas import AppointmentCreate, AppointmentResponse, AvailabilityResponse, AvailabilitySlot, BarberResponse, ServiceResponse
from app.schemas.public_config import BusinessConfigResponse
from app.services import business_rules

router = APIRouter(prefix="/api", tags=["public"])
BUSINESS_TZ = ZoneInfo(settings.business_timezone)
ACTIVE_STATUSES = ("pending", "confirmed")


@router.get("/business-config", response_model=BusinessConfigResponse)
async def business_config():
    return {"timezone": settings.business_timezone, **business_rules.public_schedule()}


@router.get("/services", response_model=list[ServiceResponse])
def list_services(db: Session = Depends(get_db)):
    return db.scalars(select(Service).where(Service.is_active.is_(True)).order_by(Service.id)).all()


@router.get("/services/{service_id}", response_model=ServiceResponse)
def get_service(service_id: int, db: Session = Depends(get_db)):
    service = db.scalar(select(Service).where(Service.id == service_id, Service.is_active.is_(True)))
    if not service:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    return service


def _business_window(db: Session, barber_id: int, requested_date: date):
    hours = db.scalar(select(BusinessHours).where(BusinessHours.barber_id == barber_id, BusinessHours.day_of_week == requested_date.weekday()))
    if not hours or not hours.is_open or not hours.opening_time or not hours.closing_time:
        return None
    return business_rules.business_window(requested_date, BUSINESS_TZ, hours.opening_time, hours.closing_time)


def _overlaps(start: datetime, end: datetime, appointments, blocked):
    return any(start < item.ends_at and end > item.starts_at for item in [*appointments, *blocked])


@router.get("/availability", response_model=AvailabilityResponse)
def availability(service_id: int, barber_id: int, date: date = Query(...), db: Session = Depends(get_db)):
    service = db.scalar(select(Service).where(Service.id == service_id, Service.is_active.is_(True)))
    if not service:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    barber = db.scalar(select(Barber).where(Barber.id == barber_id, Barber.is_active.is_(True)))
    if not barber:
        raise HTTPException(status_code=404, detail="Barbero no encontrado")
    now = datetime.now(BUSINESS_TZ)
    # Past calendar dates retain the same response contract, with no slots.
    if date < now.date():
        return {"date": date, "service_id": service_id, "barber_id": barber_id, "slots": []}
    window = _business_window(db, barber_id, date)
    if not window:
        return {"date": date, "service_id": service_id, "barber_id": barber_id, "slots": []}
    opening, closing = window
    appointments = db.scalars(select(Appointment).where(Appointment.barber_id == barber_id, Appointment.status.in_(ACTIVE_STATUSES), Appointment.starts_at < closing, Appointment.ends_at > opening)).all()
    blocked = db.scalars(select(BlockedTime).where(BlockedTime.barber_id == barber_id, BlockedTime.starts_at < closing, BlockedTime.ends_at > opening)).all()
    slots = []
    cursor = opening
    duration = timedelta(minutes=service.duration_minutes)
    while cursor + duration <= closing:
        end = cursor + duration
        if business_rules.interval_allowed(cursor, end, window, BUSINESS_TZ):
            slots.append(AvailabilitySlot(starts_at=cursor, ends_at=end, available=cursor > now and not _overlaps(cursor, end, appointments, blocked)))
        cursor += timedelta(minutes=30)
    return {"date": date, "service_id": service_id, "barber_id": barber_id, "slots": slots}

@router.get("/barbers", response_model=list[BarberResponse])
def list_barbers(db: Session = Depends(get_db)):
    return db.scalars(select(Barber).where(Barber.is_active.is_(True)).order_by(Barber.id)).all()


@router.post("/appointments", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
def create_appointment(payload: AppointmentCreate, db: Session = Depends(get_db)):
    try:
        service = db.scalar(select(Service).where(Service.id == payload.service_id, Service.is_active.is_(True)))
        if not service:
            raise HTTPException(status_code=404, detail="Servicio no encontrado")
        # key_share=True (without read=True) emits FOR NO KEY UPDATE on PostgreSQL.
        # The row lock serializes this barber's bookings until commit/rollback,
        # while remaining compatible with foreign-key KEY SHARE locks.
        barber = db.scalar(
            select(Barber)
            .where(Barber.id == payload.barber_id, Barber.is_active.is_(True))
            .with_for_update(key_share=True)
        )
        if not barber:
            raise HTTPException(status_code=404, detail="Barbero no encontrado")
        starts_at = payload.starts_at.astimezone(BUSINESS_TZ)
        ends_at = starts_at + timedelta(minutes=service.duration_minutes)
        now = datetime.now(BUSINESS_TZ)
        if starts_at <= now:
            raise HTTPException(status_code=422, detail="La cita no puede estar en el pasado")
        window = _business_window(db, payload.barber_id, starts_at.date())
        if not window or not business_rules.interval_allowed(starts_at, ends_at, window, BUSINESS_TZ):
            raise HTTPException(status_code=422, detail="El horario está fuera del horario de atención o coincide con el almuerzo")
        blocked = db.scalar(select(BlockedTime).where(BlockedTime.barber_id == payload.barber_id, BlockedTime.starts_at < ends_at, BlockedTime.ends_at > starts_at))
        if blocked:
            raise HTTPException(status_code=409, detail="El horario está bloqueado")
        appointment = Appointment(**payload.model_dump(exclude={"starts_at"}), starts_at=starts_at, ends_at=ends_at, status="pending")
        db.add(appointment)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if (
            getattr(error.orig, "sqlstate", None) == "23P01"
            and getattr(getattr(error.orig, "diag", None), "constraint_name", None)
            == "ex_appointments_active_barber_time_overlap"
        ):
            raise HTTPException(status_code=409, detail="Este horario acaba de ser reservado") from error
        raise
    except Exception:
        db.rollback()
        raise
    db.refresh(appointment)
    return appointment
