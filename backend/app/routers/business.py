"""Business profile, opening hours and the AI kill switch."""

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select

from app.deps import CurrentUserDep, TenantSessionDep, verify_origin
from app.models import Business, BusinessHours
from app.routers._helpers import OwnerDep, WriterDep
from app.schemas.business import (
    AiToggle,
    BusinessOut,
    BusinessUpdate,
    OpeningHours,
    OpeningHoursReplace,
)
from app.services import audit
from app.services.auth import CurrentUser

router = APIRouter(
    prefix="/api/v1/business", tags=["business"], dependencies=[Depends(verify_origin)]
)


async def _load(session: TenantSessionDep, current: CurrentUser) -> BusinessOut:
    business = (await session.execute(select(Business))).scalar_one()
    hours = (
        await session.execute(
            select(BusinessHours).order_by(BusinessHours.weekday, BusinessHours.opens_at)
        )
    ).scalars()
    return BusinessOut.model_validate(
        {
            **{f: getattr(business, f) for f in BusinessOut.model_fields if hasattr(business, f)},
            "ai_enabled": current.tenant.ai_enabled,
            "hours": [OpeningHours.model_validate(h) for h in hours],
        }
    )


@router.get("")
async def get_business(session: TenantSessionDep, current: CurrentUserDep) -> BusinessOut:
    return await _load(session, current)


@router.patch("")
async def update_business(
    body: BusinessUpdate, session: TenantSessionDep, current: WriterDep
) -> BusinessOut:
    business = (await session.execute(select(Business))).scalar_one()
    changed = sorted(body.model_fields_set)
    for field in changed:
        setattr(business, field, getattr(body, field))
    if "gas_safe_number" in changed:
        # A new number needs checking again before the AI may mention it.
        business.gas_safe_verified = False
    audit.record(
        session,
        tenant_id=current.tenant.id,
        actor_user_id=current.user.id,
        action="business.updated",
        details={"fields": changed},
    )
    await session.commit()
    return await _load(session, current)


@router.put("/hours")
async def replace_opening_hours(
    body: OpeningHoursReplace, session: TenantSessionDep, current: WriterDep
) -> BusinessOut:
    await session.execute(delete(BusinessHours).where(BusinessHours.tenant_id == current.tenant.id))
    session.add_all(
        BusinessHours(tenant_id=current.tenant.id, **h.model_dump()) for h in body.hours
    )
    audit.record(
        session,
        tenant_id=current.tenant.id,
        actor_user_id=current.user.id,
        action="business.hours_updated",
    )
    await session.commit()
    return await _load(session, current)


@router.put("/ai")
async def set_ai_enabled(
    body: AiToggle, session: TenantSessionDep, current: OwnerDep
) -> BusinessOut:
    """Kill switch. When off, calls go straight to the fallback number (Phase 3)."""
    current.tenant.ai_enabled = body.enabled
    audit.record(
        session,
        tenant_id=current.tenant.id,
        actor_user_id=current.user.id,
        action="tenant.ai_enabled" if body.enabled else "tenant.ai_disabled",
    )
    await session.commit()
    return await _load(session, current)
