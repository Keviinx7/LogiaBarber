from pydantic import BaseModel


class BusinessConfigResponse(BaseModel):
    timezone: str
    opening_time: str
    closing_time: str
    lunch_start: str
    lunch_end: str
    working_days: list[int]
