"""Engineers: skills, weekly hours and time off."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.deps import CurrentUserDep, TenantSessionDep, verify_origin
from app.models import Engineer, EngineerHours, EngineerService, EngineerTimeOff, Service
from app.routers._helpers import WriterDep, commit, get_owned
from app.schemas.engineers import (
    EngineerCreate,
    EngineerOut,
    EngineerUpdate,
    TimeOffCreate,
    TimeOffOut,
    WorkingHours,
)
from app.services import audit

router = APIRouter(
    prefix="/api/v1/engineers", tags=["engineers"], dependencies=[Depends(verify_origin)]
)


def _out(engineer: Engineer) -> EngineerOut:
    return EngineerOut(
        id=engineer.id,
        name=engineer.name,
        phone_e164=engineer.phone_e164,
        email=engineer.email,
        gas_safe_id=engineer.gas_safe_id,
        active=engineer.active,
        service_ids=sorted(s.service_id for s in engineer.skills),
        hours=[WorkingHours.model_validate(h) for h in engineer.hours],
    )


async def _check_services(session: AsyncSession, service_ids: list[uuid.UUID]) -> None:
    """Every service ID must be one of this tenant's services (others are invisible)."""
    unique = set(service_ids)
    if not unique:
        return
    found = (
        await session.execute(select(func.count(Service.id)).where(Service.id.in_(unique)))
    ).scalar_one()
    if found != len(unique):
        raise AppError(422, "unknown_service", "One or more services don't exist")


def _set_skills_and_hours(
    engineer: Engineer,
    service_ids: list[uuid.UUID] | None,
    hours: list[WorkingHours] | None,
) -> None:
    """Replace skills/hours through the ORM collections (delete-orphan removes old rows).

    Skills are diffed rather than rebuilt: re-adding an identical (engineer, service) row
    while the old one is still in the session would collide on the primary key.
    """
    if service_ids is not None:
        desired = set(service_ids)
        for skill in [s for s in engineer.skills if s.service_id not in desired]:
            engineer.skills.remove(skill)
        existing = {s.service_id for s in engineer.skills}
        engineer.skills.extend(
            EngineerService(tenant_id=engineer.tenant_id, service_id=sid)
            for sid in sorted(desired - existing)
        )
    if hours is not None:
        engineer.hours = [
            EngineerHours(tenant_id=engineer.tenant_id, **h.model_dump()) for h in hours
        ]


async def _reload(session: AsyncSession, engineer: Engineer) -> EngineerOut:
    await session.refresh(engineer, ["skills", "hours"])
    return _out(engineer)


@router.get("")
async def list_engineers(
    session: TenantSessionDep, _: CurrentUserDep, active: bool | None = None
) -> list[EngineerOut]:
    query = select(Engineer).order_by(Engineer.name)
    if active is not None:
        query = query.where(Engineer.active == active)
    return [_out(e) for e in (await session.execute(query)).scalars()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_engineer(
    body: EngineerCreate, session: TenantSessionDep, current: WriterDep
) -> EngineerOut:
    await _check_services(session, body.service_ids)
    engineer = Engineer(
        id=uuid.uuid7(),
        tenant_id=current.tenant.id,
        skills=[],
        hours=[],
        **body.model_dump(exclude={"service_ids", "hours"}),
    )
    _set_skills_and_hours(engineer, body.service_ids, body.hours)
    session.add(engineer)
    audit.record(
        session,
        tenant_id=current.tenant.id,
        actor_user_id=current.user.id,
        action="engineer.created",
        target_type="engineer",
        target_id=engineer.id,
    )
    await commit(session, {})
    return await _reload(session, engineer)


@router.get("/{engineer_id}")
async def get_engineer(
    engineer_id: uuid.UUID, session: TenantSessionDep, _: CurrentUserDep
) -> EngineerOut:
    return _out(await get_owned(session, Engineer, engineer_id, "Engineer"))


@router.patch("/{engineer_id}")
async def update_engineer(
    engineer_id: uuid.UUID, body: EngineerUpdate, session: TenantSessionDep, current: WriterDep
) -> EngineerOut:
    engineer = await get_owned(session, Engineer, engineer_id, "Engineer")
    if body.service_ids is not None:
        await _check_services(session, body.service_ids)
    for field in body.model_fields_set - {"service_ids", "hours"}:
        setattr(engineer, field, getattr(body, field))
    _set_skills_and_hours(engineer, body.service_ids, body.hours)
    audit.record(
        session,
        tenant_id=current.tenant.id,
        actor_user_id=current.user.id,
        action="engineer.updated",
        target_type="engineer",
        target_id=engineer.id,
        details={"fields": sorted(body.model_fields_set)},
    )
    await commit(session, {})
    return await _reload(session, engineer)


@router.delete("/{engineer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_engineer(
    engineer_id: uuid.UUID, session: TenantSessionDep, current: WriterDep
) -> Response:
    engineer = await get_owned(session, Engineer, engineer_id, "Engineer")
    await session.delete(engineer)
    audit.record(
        session,
        tenant_id=current.tenant.id,
        actor_user_id=current.user.id,
        action="engineer.deleted",
        target_type="engineer",
        target_id=engineer_id,
    )
    await commit(session, {})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- time off ---------------------------------------------------------------------------


@router.get("/{engineer_id}/time-off")
async def list_time_off(
    engineer_id: uuid.UUID,
    session: TenantSessionDep,
    _: CurrentUserDep,
    after: datetime | None = None,
) -> list[TimeOffOut]:
    await get_owned(session, Engineer, engineer_id, "Engineer")
    query = (
        select(EngineerTimeOff)
        .where(EngineerTimeOff.engineer_id == engineer_id)
        .order_by(EngineerTimeOff.starts_at)
    )
    if after is not None:
        query = query.where(EngineerTimeOff.ends_at > after)
    return [TimeOffOut.model_validate(t) for t in (await session.execute(query)).scalars()]


@router.post("/{engineer_id}/time-off", status_code=status.HTTP_201_CREATED)
async def add_time_off(
    engineer_id: uuid.UUID, body: TimeOffCreate, session: TenantSessionDep, current: WriterDep
) -> TimeOffOut:
    await get_owned(session, Engineer, engineer_id, "Engineer")
    time_off = EngineerTimeOff(
        id=uuid.uuid7(), tenant_id=current.tenant.id, engineer_id=engineer_id, **body.model_dump()
    )
    session.add(time_off)
    audit.record(
        session,
        tenant_id=current.tenant.id,
        actor_user_id=current.user.id,
        action="engineer.time_off_added",
        target_type="engineer",
        target_id=engineer_id,
    )
    await commit(session, {})
    return TimeOffOut.model_validate(time_off)


@router.delete("/{engineer_id}/time-off/{time_off_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_time_off(
    engineer_id: uuid.UUID, time_off_id: uuid.UUID, session: TenantSessionDep, current: WriterDep
) -> Response:
    time_off = await get_owned(session, EngineerTimeOff, time_off_id, "Time off")
    if time_off.engineer_id != engineer_id:
        raise AppError(404, "not_found", "Time off not found")
    await session.delete(time_off)
    audit.record(
        session,
        tenant_id=current.tenant.id,
        actor_user_id=current.user.id,
        action="engineer.time_off_removed",
        target_type="engineer",
        target_id=engineer_id,
    )
    await commit(session, {})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
