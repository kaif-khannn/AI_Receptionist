from datetime import time

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import EmergencyPolicy
from app.schemas.common import (
    Timezone,
    UkPhone,
    UkPostcode,
    Website,
    Weekday,
    check_no_overlaps,
)


class OpeningHours(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    weekday: Weekday
    opens_at: time
    closes_at: time

    @model_validator(mode="after")
    def _order(self) -> OpeningHours:
        if self.opens_at >= self.closes_at:
            raise ValueError("opens_at must be before closes_at")
        return self

    @property
    def start(self) -> time:
        return self.opens_at

    @property
    def end(self) -> time:
        return self.closes_at


class OpeningHoursReplace(BaseModel):
    hours: list[OpeningHours] = Field(max_length=28)

    @field_validator("hours")
    @classmethod
    def _no_overlaps(cls, hours: list[OpeningHours]) -> list[OpeningHours]:
        check_no_overlaps(hours)
        return sorted(hours, key=lambda h: (h.weekday, h.opens_at))


class BusinessUpdate(BaseModel):
    """Partial update: only fields sent are changed. Send null to clear an optional field."""

    company_name: str | None = Field(default=None, min_length=2, max_length=200)
    timezone: Timezone | None = None
    phone_e164: UkPhone | None = None
    email: EmailStr | None = None
    website: Website | None = None
    address_line1: str | None = Field(default=None, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    town: str | None = Field(default=None, max_length=100)
    postcode: UkPostcode | None = None
    transfer_number_e164: UkPhone | None = None
    fallback_number_e164: UkPhone | None = None
    emergency_policy: EmergencyPolicy | None = None
    gas_safe_number: str | None = Field(default=None, pattern=r"^\d{5,7}$")

    @field_validator("company_name", "timezone", "emergency_policy")
    @classmethod
    def _required_not_null(cls, value: object) -> object:
        # These have values in the DB; null would mean "clear", which isn't allowed.
        if value is None:
            raise ValueError("cannot be empty")
        return value


class BusinessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_name: str
    timezone: str
    phone_e164: str | None
    email: str | None
    website: str | None
    address_line1: str | None
    address_line2: str | None
    town: str | None
    postcode: str | None
    transfer_number_e164: str | None
    fallback_number_e164: str | None
    emergency_policy: EmergencyPolicy
    gas_safe_number: str | None
    gas_safe_verified: bool
    ai_enabled: bool
    hours: list[OpeningHours]


class AiToggle(BaseModel):
    enabled: bool
