from decimal import Decimal

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Barber, BusinessHours, Service
from app.services.business_rules import CLOSING_TIME, OPENING_TIME, WORKING_DAYS


def seed():
    with SessionLocal.begin() as db:
        service_data = [
            ("Corte clásico", "Líneas limpias y acabado preciso.", Decimal("5.00"), 30),
            ("Corte + barba", "El ritual completo para salir impecable.", Decimal("7.00"), 45),
            ("Barba", "Perfilado, cuidado y toalla caliente.", Decimal("3.00"), 20),
        ]
        for name, description, price, duration in service_data:
            service = db.scalar(select(Service).where(Service.name == name))
            if service:
                service.description, service.price, service.duration_minutes, service.is_active = description, price, duration, True
            else:
                db.add(Service(name=name, description=description, price=price, duration_minutes=duration, is_active=True))
        barbers = []
        for name in ("Barbero 1", "Barbero 2"):
            barber = db.scalar(select(Barber).where(Barber.name == name))
            if not barber:
                barber = Barber(name=name, is_active=True)
                db.add(barber); db.flush()
            barber.is_active = True; barbers.append(barber)
        for barber in barbers:
            for day in WORKING_DAYS:
                hours = db.scalar(select(BusinessHours).where(BusinessHours.barber_id == barber.id, BusinessHours.day_of_week == day))
                if not hours:
                    db.add(BusinessHours(barber_id=barber.id, day_of_week=day, is_open=True,
                                         opening_time=OPENING_TIME, closing_time=CLOSING_TIME))
        # Lunch is a recurring rule, not dated BlockedTime rows. Historical
        # lunch blocks remain untouched; cleanup requires a separate audit.


if __name__ == "__main__":
    seed()
    print("Seed aplicado correctamente.")
