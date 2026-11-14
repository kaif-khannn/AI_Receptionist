import uuid
from datetime import datetime, time

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.schemas.common import UkPhone, Weekday, check_no_overlaps


class WorkingHours(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    weekday: Weekday
    starts_at: time
    ends_at: time

    @model_validator(mode="after")
    def _order(self) -> WorkingHours:
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be before ends_at")
        return self

    @property
    def start(self) -> time:
        return self.starts_at

    @property
    def end(self) -> time:
        return self.ends_at


def _check_hours(hours: list[WorkingHours] | None) -> list[WorkingHours] | None:
    if hours is None:
        return None
    check_no_overlaps(hours)
    return sorted(hours, key=lambda h: (h.weekday, h.starts_at))


class EngineerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone_e164: UkPhone | None = None
    email: EmailStr | None = None
    gas_safe_id: str | None = Field(default=None, pattern=r"^\d{5,8}$")
    active: bool = True
    service_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    hours: list[WorkingHours] = Field(default_factory=list, max_length=28)

    @field_validator("hours")
    @classmethod
    def _hours(cls, hours: list[WorkingHours]) -> list[WorkingHours]:
        return _check_hours(hours) or []


class EngineerUpdate(BaseModel):
    """Partial update. ``service_ids`` and ``hours``, if sent, replace the whole list."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone_e164: UkPhone | None = None
    email: EmailStr | None = None
    gas_safe_id: str | None = Field(default=None, pattern=r"^\d{5,8}$")
    active: bool | None = None
    service_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)
    hours: list[WorkingHours] | None = Field(default=None, max_length=28)

    @field_validator("name", "active", "service_ids", "hours")
    @classmethod
    def _not_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("cannot be empty")
        return value

    @field_validator("hours")
    @classmethod
    def _hours(cls, hours: list[WorkingHours] | None) -> list[WorkingHours] | None:
        return _check_hours(hours)


class EngineerOut(BaseModel):
    id: uuid.UUID
    name: str
    phone_e164: str | None
    email: str | None
    gas_safe_id: str | None
    active: bool
    service_ids: list[uuid.UUID]
    hours: list[WorkingHours]


class TimeOffCreate(BaseModel):
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    reason: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _order(self) -> TimeOffCreate:
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be before ends_at")
        return self


class TimeOffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    engineer_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    reason: str | None
