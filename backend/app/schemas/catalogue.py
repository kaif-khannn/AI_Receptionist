import uuid

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from app.models import PriceType, ServiceCategory
from app.schemas.common import PostcodePrefix, UkPostcode

MAX_PRICE_MINOR = 10_000_000  # £100,000: catches a price entered in pence twice over


def format_price(price_type: PriceType, price_minor: int | None) -> str:
    """How the price is shown to owners and read to callers."""
    if price_type == PriceType.QUOTE or price_minor is None:
        return "Priced after a survey"
    pounds, pence = divmod(price_minor, 100)
    amount = f"£{pounds:,}" if pence == 0 else f"£{pounds:,}.{pence:02d}"
    return f"from {amount}" if price_type == PriceType.FROM else amount


# ---- services ---------------------------------------------------------------------------


class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: ServiceCategory
    description: str | None = Field(default=None, max_length=2000)
    default_duration_min: int = Field(default=60, ge=15, le=1440)
    active: bool = True


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: ServiceCategory | None = None
    description: str | None = Field(default=None, max_length=2000)
    default_duration_min: int | None = Field(default=None, ge=15, le=1440)
    active: bool | None = None

    @field_validator("name", "category", "default_duration_min", "active")
    @classmethod
    def _not_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("cannot be empty")
        return value


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category: ServiceCategory
    description: str | None
    default_duration_min: int
    active: bool


# ---- packages ---------------------------------------------------------------------------


class PackageFeatureIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feature: str = Field(min_length=1, max_length=300)
    included: bool = True
    conditions: str | None = Field(default=None, max_length=300)


class _PriceChecks(BaseModel):
    price_type: PriceType | None = None
    price_minor: int | None = Field(default=None, ge=0, le=MAX_PRICE_MINOR)

    def _check_price(self) -> None:
        if self.price_type == PriceType.QUOTE and self.price_minor is not None:
            raise ValueError("price_minor must be empty when price_type is 'quote'")
        if self.price_type in (PriceType.FIXED, PriceType.FROM) and self.price_minor is None:
            raise ValueError("price_minor is required for fixed and 'from' prices")


class PackageCreate(_PriceChecks):
    service_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    price_type: PriceType
    active: bool = True
    sort_order: int = Field(default=0, ge=0, le=1000)
    features: list[PackageFeatureIn] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def _price(self) -> PackageCreate:
        self._check_price()
        return self


class PackageUpdate(_PriceChecks):
    """Partial update. ``features``, if sent, replaces the whole list. To change the price,
    send ``price_type`` (and ``price_minor`` unless it's a quote)."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=1000)
    features: list[PackageFeatureIn] | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def _price(self) -> PackageUpdate:
        sent = self.model_fields_set
        if "price_minor" in sent and "price_type" not in sent:
            raise ValueError("send price_type together with price_minor")
        if "price_type" in sent:
            if self.price_type is None:
                raise ValueError("price_type cannot be empty")
            self._check_price()
        return self


class PackageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_id: uuid.UUID
    name: str
    description: str | None
    price_type: PriceType
    price_minor: int | None
    currency: str
    active: bool
    sort_order: int
    features: list[PackageFeatureIn]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def price_display(self) -> str:
        return format_price(self.price_type, self.price_minor)


# ---- coverage ---------------------------------------------------------------------------


class ServiceAreasReplace(BaseModel):
    prefixes: list[PostcodePrefix] = Field(max_length=500)

    @field_validator("prefixes")
    @classmethod
    def _dedupe(cls, prefixes: list[str]) -> list[str]:
        return sorted(set(prefixes))


class ServiceAreasOut(BaseModel):
    prefixes: list[str]


class CoverageCheck(BaseModel):
    postcode: UkPostcode


class CoverageResult(BaseModel):
    postcode: str
    covered: bool
