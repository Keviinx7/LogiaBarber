from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated, Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator


# Strip only exterior whitespace; preserve names and international phone formats.
ClientName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
ClientPhone = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserResponse(ORMModel):
    id: int
    name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = None
    price: Decimal = Field(ge=0, decimal_places=2)
    duration_minutes: int = Field(gt=0)
    is_active: bool = True


class ServiceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = None
    price: Optional[Decimal] = Field(default=None, ge=0, decimal_places=2)
    duration_minutes: Optional[int] = Field(default=None, gt=0)
    is_active: Optional[bool] = None


class ServiceResponse(ServiceCreate, ORMModel):
    id: int
    created_at: datetime
    updated_at: datetime

class BarberResponse(ORMModel):
    id: int
    name: str


class AppointmentCreate(BaseModel):
    client_name: ClientName
    client_phone: ClientPhone
    service_id: int = Field(gt=0)
    barber_id: int = Field(gt=0)
    starts_at: AwareDatetime
    notes: Optional[str] = None

class AppointmentUpdate(BaseModel):
    client_name: Optional[ClientName] = None
    client_phone: Optional[ClientPhone] = None
    service_id: Optional[int] = Field(default=None, gt=0)
    barber_id: Optional[int] = Field(default=None, gt=0)
    starts_at: Optional[AwareDatetime] = None
    ends_at: Optional[AwareDatetime] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class AppointmentResponse(AppointmentCreate, ORMModel):
    id: int
    created_at: datetime
    updated_at: datetime
    ends_at: datetime
    status: str


class AvailabilitySlot(BaseModel):
    starts_at: datetime
    ends_at: datetime
    available: bool


class AvailabilityResponse(BaseModel):
    date: date
    service_id: int
    barber_id: int
    slots: list[AvailabilitySlot]


class BusinessHoursCreate(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    opening_time: Optional[time] = None
    closing_time: Optional[time] = None
    is_open: bool = True

    @model_validator(mode="after")
    def validate_hours(self):
        if self.is_open and (self.opening_time is None or self.closing_time is None or self.closing_time <= self.opening_time):
            raise ValueError("el horario abierto requiere cierre posterior a apertura")
        return self


class BusinessHoursUpdate(BusinessHoursCreate):
    pass


class BusinessHoursResponse(BusinessHoursCreate, ORMModel):
    id: int


class BlockedTimeCreate(BaseModel):
    starts_at: datetime
    ends_at: datetime
    reason: Optional[str] = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_times(self):
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("starts_at y ends_at deben incluir zona horaria")
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at debe ser posterior a starts_at")
        return self


class BlockedTimeResponse(BlockedTimeCreate, ORMModel):
    id: int
    created_at: datetime
