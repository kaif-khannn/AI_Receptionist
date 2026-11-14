import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import UserRole


class SignupRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    # NCSC guidance: favour length over complexity rules.
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    ai_enabled: bool


class MeResponse(BaseModel):
    user: UserOut
    tenant: TenantOut
