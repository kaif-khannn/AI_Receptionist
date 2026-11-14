"""Phase 2: business profile, hours, services, packages, coverage and engineers."""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError

from app.core.config import Settings
from app.main import create_app
from tests.conftest import add_user, run_sql, signup

pytestmark = pytest.mark.db

PASSWORD = "correct horse battery"


@pytest.fixture
def owner(db_client: TestClient) -> TestClient:
    signup(db_client, email="owner@abc-heating.example.com", company="ABC Heating")
    return db_client


@pytest.fixture
def tenant_id(owner: TestClient) -> str:
    tid: str = owner.get("/api/v1/me").json()["tenant"]["id"]
    return tid


def _client_for(settings: Settings, email: str) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert response.status_code == 200, response.text
        yield client


@pytest.fixture
def manager(db_settings: Settings, owner_url: str, tenant_id: str) -> Iterator[TestClient]:
    add_user(owner_url, tenant_id, "manager@abc-heating.example.com", "manager", PASSWORD)
    yield from _client_for(db_settings, "manager@abc-heating.example.com")


@pytest.fixture
def engineer_user(db_settings: Settings, owner_url: str, tenant_id: str) -> Iterator[TestClient]:
    add_user(owner_url, tenant_id, "eng@abc-heating.example.com", "engineer", PASSWORD)
    yield from _client_for(db_settings, "eng@abc-heating.example.com")


@pytest.fixture
def other_tenant(db_settings: Settings, owner: TestClient) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as client:
        signup(client, email="owner@london-boiler.example.com", company="London Boiler Care")
        yield client


def make_service(client: TestClient, name: str = "Boiler repair", **extra: Any) -> dict[str, Any]:
    response = client.post(
        "/api/v1/services", json={"name": name, "category": "boiler_repair", **extra}
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def make_package(client: TestClient, service_id: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "service_id": service_id,
        "name": "Essential",
        "price_type": "from",
        "price_minor": 185000,
        "features": [
            {"feature": "A-rated combi boiler", "included": True},
            {"feature": "Power flush", "included": False, "conditions": "Available as add-on"},
        ],
        **extra,
    }
    response = client.post("/api/v1/packages", json=payload)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


# ---- business profile -------------------------------------------------------------------


def test_business_defaults(owner: TestClient) -> None:
    body = owner.get("/api/v1/business").json()
    assert body["company_name"] == "ABC Heating"
    assert body["timezone"] == "Europe/London"
    assert body["emergency_policy"] == "callback"
    assert body["ai_enabled"] is True
    assert body["gas_safe_verified"] is False
    assert body["hours"] == []


def test_business_update_normalises_uk_details(owner: TestClient) -> None:
    response = owner.patch(
        "/api/v1/business",
        json={
            "phone_e164": "07911 123456",
            "transfer_number_e164": "+44 7911 654321",
            "postcode": "sw1a1aa",
            "website": "abc-heating.example.com",
            "emergency_policy": "transfer",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["phone_e164"] == "+447911123456"
    assert body["transfer_number_e164"] == "+447911654321"
    assert body["postcode"] == "SW1A 1AA"
    assert body["website"] == "https://abc-heating.example.com"
    assert body["emergency_policy"] == "transfer"


@pytest.mark.parametrize(
    "payload",
    [
        {"phone_e164": "12345"},
        {"phone_e164": "+1 202 555 0143"},
        {"postcode": "NOT A POSTCODE"},
        {"timezone": "Mars/Olympus"},
        {"company_name": None},
        {"gas_safe_number": "abc"},
    ],
)
def test_business_update_rejects_bad_input(owner: TestClient, payload: dict[str, Any]) -> None:
    assert owner.patch("/api/v1/business", json=payload).status_code == 422


def test_changing_gas_safe_number_clears_verification(
    owner: TestClient, owner_url: str, tenant_id: str
) -> None:
    owner.patch("/api/v1/business", json={"gas_safe_number": "123456"})
    run_sql(
        owner_url,
        "UPDATE businesses SET gas_safe_verified = true WHERE tenant_id = :t",
        params={"t": tenant_id},
    )
    assert owner.get("/api/v1/business").json()["gas_safe_verified"] is True
    body = owner.patch("/api/v1/business", json={"gas_safe_number": "654321"}).json()
    assert body["gas_safe_verified"] is False


def test_opening_hours_replace(owner: TestClient) -> None:
    hours = [
        {"weekday": 0, "opens_at": "13:00", "closes_at": "17:30"},
        {"weekday": 0, "opens_at": "08:00", "closes_at": "12:00"},
        {"weekday": 5, "opens_at": "09:00", "closes_at": "13:00"},
    ]
    body = owner.put("/api/v1/business/hours", json={"hours": hours}).json()
    assert [(h["weekday"], h["opens_at"]) for h in body["hours"]] == [
        (0, "08:00:00"),
        (0, "13:00:00"),
        (5, "09:00:00"),
    ]
    # Replacing again removes the old rows.
    body = owner.put(
        "/api/v1/business/hours",
        json={"hours": [{"weekday": 1, "opens_at": "08:00", "closes_at": "18:00"}]},
    ).json()
    assert len(body["hours"]) == 1


@pytest.mark.parametrize(
    "hours",
    [
        [{"weekday": 0, "opens_at": "17:00", "closes_at": "09:00"}],
        [
            {"weekday": 2, "opens_at": "08:00", "closes_at": "13:00"},
            {"weekday": 2, "opens_at": "12:00", "closes_at": "17:00"},
        ],
        [{"weekday": 7, "opens_at": "08:00", "closes_at": "17:00"}],
    ],
)
def test_opening_hours_validation(owner: TestClient, hours: list[dict[str, Any]]) -> None:
    assert owner.put("/api/v1/business/hours", json={"hours": hours}).status_code == 422


def test_kill_switch_is_owner_only(owner: TestClient, manager: TestClient) -> None:
    assert manager.put("/api/v1/business/ai", json={"enabled": False}).status_code == 403
    body = owner.put("/api/v1/business/ai", json={"enabled": False}).json()
    assert body["ai_enabled"] is False
    assert owner.get("/api/v1/me").json()["tenant"]["ai_enabled"] is False


# ---- roles ------------------------------------------------------------------------------


def test_engineer_role_can_read_but_not_write(owner: TestClient, engineer_user: TestClient) -> None:
    make_service(owner)
    assert engineer_user.get("/api/v1/services").status_code == 200
    assert engineer_user.get("/api/v1/business").status_code == 200
    assert (
        engineer_user.post("/api/v1/services", json={"name": "X", "category": "other"}).status_code
        == 403
    )
    assert engineer_user.patch("/api/v1/business", json={"town": "Leeds"}).status_code == 403


def test_manager_can_configure(manager: TestClient) -> None:
    make_service(manager, "Annual service")
    assert manager.patch("/api/v1/business", json={"town": "Manchester"}).status_code == 200


# ---- services ---------------------------------------------------------------------------


def test_service_crud(owner: TestClient, owner_url: str) -> None:
    created = make_service(owner, "Boiler repair", default_duration_min=90)
    assert created["default_duration_min"] == 90
    sid = created["id"]

    assert owner.get(f"/api/v1/services/{sid}").json()["name"] == "Boiler repair"
    updated = owner.patch(f"/api/v1/services/{sid}", json={"active": False}).json()
    assert updated["active"] is False
    assert owner.get("/api/v1/services", params={"active": True}).json() == []
    assert owner.delete(f"/api/v1/services/{sid}").status_code == 204
    assert owner.get(f"/api/v1/services/{sid}").status_code == 404

    actions = [
        r.action for r in run_sql(owner_url, "SELECT action FROM audit_logs ORDER BY created_at")
    ]
    assert actions[-3:] == ["service.created", "service.updated", "service.deleted"]
    (row,) = run_sql(
        owner_url, "SELECT target_id::text AS tid FROM audit_logs WHERE action = 'service.created'"
    )
    assert row.tid == sid


def test_duplicate_service_name_is_conflict(owner: TestClient) -> None:
    make_service(owner, "Boiler Repair")
    response = owner.post("/api/v1/services", json={"name": "boiler repair", "category": "other"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "service_name_taken"


def test_service_validation(owner: TestClient) -> None:
    for payload in (
        {"name": "", "category": "boiler_repair"},
        {"name": "X", "category": "plumbing"},
        {"name": "X", "category": "other", "default_duration_min": 5},
    ):
        assert owner.post("/api/v1/services", json=payload).status_code == 422


# ---- packages ---------------------------------------------------------------------------


def test_package_create_with_features_and_price_display(owner: TestClient) -> None:
    service = make_service(owner, "Boiler installation", category="boiler_installation")
    package = make_package(owner, service["id"])
    assert package["price_display"] == "from £1,850"
    assert package["currency"] == "GBP"
    assert [f["feature"] for f in package["features"]] == ["A-rated combi boiler", "Power flush"]
    assert package["features"][1]["included"] is False

    quote = make_package(owner, service["id"], name="Premium", price_type="quote", price_minor=None)
    assert quote["price_display"] == "Priced after a survey"

    listed = owner.get("/api/v1/packages", params={"service_id": service["id"]}).json()
    assert {p["name"] for p in listed} == {"Essential", "Premium"}


@pytest.mark.parametrize(
    ("price_type", "price_minor"),
    [("quote", 50000), ("fixed", None), ("from", -1), ("fixed", 100_000_000)],
)
def test_package_price_rules(owner: TestClient, price_type: str, price_minor: int | None) -> None:
    service = make_service(owner)
    response = owner.post(
        "/api/v1/packages",
        json={
            "service_id": service["id"],
            "name": "Bad",
            "price_type": price_type,
            "price_minor": price_minor,
        },
    )
    assert response.status_code == 422


def test_package_update_replaces_features(owner: TestClient, owner_url: str) -> None:
    service = make_service(owner)
    package = make_package(owner, service["id"])
    body = owner.patch(
        f"/api/v1/packages/{package['id']}",
        json={
            "features": [{"feature": "Magnetic filter"}],
            "price_type": "fixed",
            "price_minor": 199900,
        },
    ).json()
    assert [f["feature"] for f in body["features"]] == ["Magnetic filter"]
    assert body["price_display"] == "£1,999"
    (row,) = run_sql(owner_url, "SELECT count(*) AS n FROM package_features")
    assert row.n == 1  # old features deleted, not orphaned

    # Price must come with its type.
    response = owner.patch(f"/api/v1/packages/{package['id']}", json={"price_minor": 100})
    assert response.status_code == 422


def test_cannot_delete_service_that_has_packages(owner: TestClient) -> None:
    service = make_service(owner)
    package = make_package(owner, service["id"])
    response = owner.delete(f"/api/v1/services/{service['id']}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "service_in_use"
    assert owner.delete(f"/api/v1/packages/{package['id']}").status_code == 204
    assert owner.delete(f"/api/v1/services/{service['id']}").status_code == 204


# ---- service areas ----------------------------------------------------------------------


def test_service_areas_replace_and_check(owner: TestClient) -> None:
    body = owner.put(
        "/api/v1/service-areas", json={"prefixes": ["m1", " sw1a ", "M1", "LS"]}
    ).json()
    assert body["prefixes"] == ["LS", "M1", "SW1A"]

    def covered(postcode: str) -> bool:
        response = owner.post("/api/v1/service-areas/check", json={"postcode": postcode})
        assert response.status_code == 200, response.text
        result: bool = response.json()["covered"]
        return result

    assert covered("m1 1ae")
    assert not covered("M2 1AA")
    assert covered("LS1 4AP")  # whole Leeds area
    assert covered("SW1A 1AA")

    assert owner.put("/api/v1/service-areas", json={"prefixes": ["123"]}).status_code == 422
    assert owner.post("/api/v1/service-areas/check", json={"postcode": "nope"}).status_code == 422


# ---- engineers --------------------------------------------------------------------------


def test_engineer_crud_with_skills_and_hours(owner: TestClient) -> None:
    repair = make_service(owner, "Boiler repair")
    servicing = make_service(owner, "Annual service", category="boiler_servicing")
    created = owner.post(
        "/api/v1/engineers",
        json={
            "name": "Dave Smith",
            "phone_e164": "07911 123456",
            "gas_safe_id": "1234567",
            "service_ids": [repair["id"], servicing["id"]],
            "hours": [
                {"weekday": 0, "starts_at": "08:00", "ends_at": "17:00"},
                {"weekday": 1, "starts_at": "08:00", "ends_at": "17:00"},
            ],
        },
    )
    assert created.status_code == 201, created.text
    eng = created.json()
    assert eng["phone_e164"] == "+447911123456"
    assert sorted(eng["service_ids"]) == sorted([repair["id"], servicing["id"]])
    assert len(eng["hours"]) == 2

    # Replace skills keeping one that already exists (exercises the diff path).
    updated = owner.patch(
        f"/api/v1/engineers/{eng['id']}",
        json={
            "service_ids": [repair["id"]],
            "hours": [{"weekday": 4, "starts_at": "09:00", "ends_at": "15:00"}],
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["service_ids"] == [repair["id"]]
    assert [h["weekday"] for h in body["hours"]] == [4]

    assert owner.delete(f"/api/v1/engineers/{eng['id']}").status_code == 204
    assert owner.get(f"/api/v1/engineers/{eng['id']}").status_code == 404


def test_engineer_validation(owner: TestClient) -> None:
    overlapping = [
        {"weekday": 0, "starts_at": "08:00", "ends_at": "13:00"},
        {"weekday": 0, "starts_at": "12:00", "ends_at": "17:00"},
    ]
    assert (
        owner.post("/api/v1/engineers", json={"name": "A", "hours": overlapping}).status_code == 422
    )
    response = owner.post(
        "/api/v1/engineers", json={"name": "A", "service_ids": [str(uuid.uuid4())]}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_service"


def test_engineer_time_off(owner: TestClient) -> None:
    eng = owner.post("/api/v1/engineers", json={"name": "Dave"}).json()
    url = f"/api/v1/engineers/{eng['id']}/time-off"
    created = owner.post(
        url,
        json={
            "starts_at": "2026-12-24T00:00:00Z",
            "ends_at": "2026-12-27T00:00:00Z",
            "reason": "Christmas",
        },
    )
    assert created.status_code == 201, created.text
    assert len(owner.get(url).json()) == 1
    # Naive datetimes are ambiguous (GMT or BST?) and rejected.
    naive = owner.post(
        url, json={"starts_at": "2026-12-28T09:00:00", "ends_at": "2026-12-28T17:00:00"}
    )
    assert naive.status_code == 422
    backwards = owner.post(
        url, json={"starts_at": "2026-12-28T17:00:00Z", "ends_at": "2026-12-28T09:00:00Z"}
    )
    assert backwards.status_code == 422
    assert owner.delete(f"{url}/{created.json()['id']}").status_code == 204
    assert owner.get(url).json() == []


# ---- cross-tenant -----------------------------------------------------------------------


def test_other_tenant_cannot_see_or_touch_resources(
    owner: TestClient, other_tenant: TestClient
) -> None:
    service = make_service(owner)
    package = make_package(owner, service["id"])
    eng = owner.post("/api/v1/engineers", json={"name": "Dave"}).json()

    assert other_tenant.get("/api/v1/services").json() == []
    assert other_tenant.get("/api/v1/packages").json() == []
    assert other_tenant.get("/api/v1/engineers").json() == []
    for path in (
        f"/api/v1/services/{service['id']}",
        f"/api/v1/packages/{package['id']}",
        f"/api/v1/engineers/{eng['id']}",
    ):
        assert other_tenant.get(path).status_code == 404
        assert other_tenant.patch(path, json={"name": "Hijacked"}).status_code == 404
        assert other_tenant.delete(path).status_code == 404
    assert owner.get(f"/api/v1/services/{service['id']}").json()["name"] == "Boiler repair"


def test_cannot_link_to_another_tenants_service_via_api(
    owner: TestClient, other_tenant: TestClient
) -> None:
    service = make_service(owner)
    response = other_tenant.post(
        "/api/v1/packages",
        json={"service_id": service["id"], "name": "X", "price_type": "fixed", "price_minor": 1},
    )
    assert response.status_code == 404
    response = other_tenant.post(
        "/api/v1/engineers", json={"name": "X", "service_ids": [service["id"]]}
    )
    assert response.status_code == 422


def test_composite_fk_blocks_cross_tenant_links_in_sql(
    owner: TestClient, other_tenant: TestClient, app_url: str
) -> None:
    """Even raw SQL as the app role can't point a package at another tenant's service:
    FK checks bypass RLS, which is why the FKs include tenant_id."""
    service = make_service(owner)
    other_tid = other_tenant.get("/api/v1/me").json()["tenant"]["id"]
    with pytest.raises(DBAPIError, match="foreign key"):
        run_sql(
            app_url,
            f"SELECT set_config('app.tenant_id', '{other_tid}', true)",
            "INSERT INTO packages (id, tenant_id, service_id, name, price_type, price_minor)"
            f" VALUES (gen_random_uuid(), '{other_tid}', '{service['id']}', 'X', 'fixed', 1)",
        )
