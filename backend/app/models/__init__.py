"""SQLAlchemy models. Importing this package registers every table on Base.metadata."""

from app.models.audit_log import AuditLog
from app.models.auth_session import AuthSession
from app.models.base import Base
from app.models.business import Business, BusinessHours, EmergencyPolicy
from app.models.catalogue import (
    Package,
    PackageFeature,
    PriceType,
    Service,
    ServiceArea,
    ServiceCategory,
)
from app.models.engineer import Engineer, EngineerHours, EngineerService, EngineerTimeOff
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserRole, UserStatus

__all__ = [
    "AuditLog",
    "AuthSession",
    "Base",
    "Business",
    "BusinessHours",
    "EmergencyPolicy",
    "Engineer",
    "EngineerHours",
    "EngineerService",
    "EngineerTimeOff",
    "Package",
    "PackageFeature",
    "PriceType",
    "Service",
    "ServiceArea",
    "ServiceCategory",
    "Tenant",
    "TenantStatus",
    "User",
    "UserRole",
    "UserStatus",
]
