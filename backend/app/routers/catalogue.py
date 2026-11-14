"""Services, packages and service areas."""

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import delete, select

from app.core.uk import postcode_is_covered
from app.deps import CurrentUserDep, TenantSessionDep, verify_origin
from app.models import Package, PackageFeature, Service, ServiceArea
from app.routers._helpers import WriterDep, commit, get_owned
from app.schemas.catalogue import (
    CoverageCheck,
    CoverageResult,
    PackageCreate,
    PackageOut,
    PackageUpdate,
    ServiceAreasOut,
    ServiceAreasReplace,
    ServiceCreate,
    ServiceOut,
    ServiceUpdate,
)
from app.services import audit

router = APIRouter(prefix="/api/v1", tags=["catalogue"], dependencies=[Depends(verify_origin)])

SERVICE_CONFLICTS = {
    "uq_services_tenant_name": ("service_name_taken", "You already have a service with that name"),
    "fk_packages_tenant_id_services": (
        "service_in_use",
        "This service still has packages. Delete them first, or mark the service inactive.",
    ),
}


# ---- services ---------------------------------------------------------------------------


@router.get("/services")
async def list_services(
    session: TenantSessionDep, _: CurrentUserDep, active: bool | None = None
) -> list[ServiceOut]:
    query = select(Service).order_by(Service.name)
    if active is not None:
        query = query.where(Service.active == active)
    return [ServiceOut.model_validate(s) for s in (await session.execute(query)).scalars()]


@router.post("/services", status_code=status.HTTP_201_CREATED)
async def create_service(
    body: ServiceCreate, session: TenantSessionDep, current: WriterDep
) -> ServiceOut:
    service = Service(id=uuid.uuid7(), tenant_id=current.tenant.id, **body.model_dump())
    session.add(service)
    audit.record(
        session,
        tenant_id=current.tenant.id,
        actor_user_id=current.user.id,
        action="service.created",
        target_type="service",
        target_id=service.id,
    )
    await commit(session, SERVICE_CONFLICTS)
    return ServiceOut.model_validate(service)


@router.get("/services/{service_id}")
async def get_service(
    service_id: uuid.UUID, session: TenantSessionDep, _: CurrentUserDep
) -> ServiceOut:
    return ServiceOut.model_validate(await get_owned(session, Service, service_id, "Service"))


@router.patch("/services/{service_id}")
async def update_service(
    service_id: uuid.UUID, body: ServiceUpdate, session: TenantSessionDep, current: WriterDep
) -> ServiceOut:
    service = await get_owned(session, Service, service_id, "Service")
    for field in body.model_fields_set:
        setattr(service, field, getattr(body, field))
    audit.record(
        session,
        tenant_id=current.tenant.id,
        actor_user_id=current.user.id,
        action="service.updated",
        target_type="service",
        target_id=service.id,
        details={"fields": sorted(body.model_fields_set)},
    )
    await commit(session, SERVICE_CONFLICTS)
    return ServiceOut.model_validate(service)


@router.delete("/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    service_id: uuid.UUID, session: TenantSessionDep, current: WriterDep
) -> Response:
    service = await get_owned(session, Service, service_id, "Service")
    await session.delete(service)
    audit.record(
        session,
        tenant_id=current.tenant.id,
        actor_user_id=current.user.id,
        action="service.deleted",
        target_type="service",
        target_id=service_id,
    )
    await commit(session, SERVICE_CONFLICTS)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- packages ---------------------------------------------------------------------------


def _features(tenant_id: uuid.UUID, body: PackageCreate | PackageUpdate) -> list[PackageFeature]:
    return [
        PackageFeature(tenant_id=tenant_id, sort_order=i, **f.model_dump())
        for i, f in enumerate(body.features or [])
    ]


@router.get("/packages")
async def list_packages(
    session: TenantSessionDep,
    _: CurrentUserDep,
    service_id: uuid.UUID | None = None,
    active: bool | None = None,
) -> list[PackageOut]:
    query = select(Package).order_by(Package.sort_order, Package.name)
    if service_id is not None:
        query = query.where(Package.service_id == service_id)
    if active is not None:
        query = query.where(Package.active == active)
    return [PackageOut.model_validate(p) for p in (await session.execute(query)).scalars()]


@router.post("/packages", status_code=status.HTTP_201_CREATED)
async def create_package(
    body: PackageCreate, session: TenantSessionDep, current: WriterDep
) -> PackageOut:
    # 404 if the service is another tenant's (invisible under RLS) or doesn't exist.
    await get_owned(session, Service, body.service_id, "Service")
    package = Package(
        id=uuid.uuid7(),
        tenant_id=current.tenant.id,
        currency="GBP",
        features=_features(current.tenant.id, body),
        **body.model_dump(exclude={"features"}),
    )
    session.add(package)
    audit.record(
        session,
        tenant_id=current.tenant.id,
        actor_user_id=current.user.id,
        action="package.created",
        target_type="package",
        target_id=package.id,
    )
    await commit(session, {})
    return PackageOut.model_validate(package)


@router.get("/packages/{package_id}")
async def get_package(
    package_id: uuid.UUID, session: TenantSessionDep, _: CurrentUserDep
) -> PackageOut:
    return PackageOut.model_validate(await get_owned(session, Package, package_id, "Package"))


@router.patch("/packages/{package_id}")
async def update_package(
    package_id: uuid.UUID, body: PackageUpdate, session: TenantSessionDep, current: WriterDep
) -> PackageOut:
    package = await get_owned(session, Package, package_id, "Package")
    for field in body.model_fields_set - {"features"}:
        setattr(package, field, getattr(body, field))
    if "features" in body.model_fields_set:
        package.features = _features(current.tenant.id, body)
    audit.record(
        session,
        tenant_id=current.tenant.id,
        actor_user_id=current.user.id,
        action="package.updated",
        target_type="package",
        target_id=package.id,
        details={"fields": sorted(body.model_fields_set)},
    )
    await commit(session, {})
    await session.refresh(package, ["features"])
    return PackageOut.model_validate(package)


@router.delete("/packages/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_package(
    package_id: uuid.UUID, session: TenantSessionDep, current: WriterDep
) -> Response:
    package = await get_owned(session, Package, package_id, "Package")
    await session.delete(package)
    audit.record(
        session,
        tenant_id=current.tenant.id,
        actor_user_id=current.user.id,
        action="package.deleted",
        target_type="package",
        target_id=package_id,
    )
    await commit(session, {})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- service areas ----------------------------------------------------------------------


async def _prefixes(session: TenantSessionDep) -> list[str]:
    rows = await session.execute(select(ServiceArea.prefix).order_by(ServiceArea.prefix))
    return list(rows.scalars())


@router.get("/service-areas")
async def get_service_areas(session: TenantSessionDep, _: CurrentUserDep) -> ServiceAreasOut:
    return ServiceAreasOut(prefixes=await _prefixes(session))


@router.put("/service-areas")
async def replace_service_areas(
    body: ServiceAreasReplace, session: TenantSessionDep, current: WriterDep
) -> ServiceAreasOut:
    await session.execute(delete(ServiceArea).where(ServiceArea.tenant_id == current.tenant.id))
    session.add_all(ServiceArea(tenant_id=current.tenant.id, prefix=p) for p in body.prefixes)
    audit.record(
        session,
        tenant_id=current.tenant.id,
        actor_user_id=current.user.id,
        action="service_areas.updated",
        details={"count": len(body.prefixes)},
    )
    await session.commit()
    return ServiceAreasOut(prefixes=await _prefixes(session))


@router.post("/service-areas/check")
async def check_coverage(
    body: CoverageCheck, session: TenantSessionDep, _: CurrentUserDep
) -> CoverageResult:
    prefixes = await _prefixes(session)
    return CoverageResult(
        postcode=body.postcode, covered=postcode_is_covered(body.postcode, prefixes)
    )
