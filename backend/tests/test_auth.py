import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.main import create_app
from tests.conftest import run_sql, signup

pytestmark = pytest.mark.db

PASSWORD = "correct horse battery"


def login(client: TestClient, email: str, password: str = PASSWORD) -> int:
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    ).status_code


def test_signup_creates_tenant_owner_and_session(db_client: TestClient, owner_url: str) -> None:
    body = signup(db_client)
    assert body["user"]["role"] == "owner"
    assert body["tenant"]["name"] == "ABC Heating"
    assert body["tenant"]["slug"].startswith("abc-heating-")
    assert "password" not in str(body)

    me = db_client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "owner@abc-heating.example.com"

    rows = run_sql(owner_url, "SELECT company_name FROM businesses")
    assert [r.company_name for r in rows] == ["ABC Heating"]
    actions = run_sql(owner_url, "SELECT action FROM audit_logs")
    assert [r.action for r in actions] == ["tenant.signup"]


def test_password_is_stored_as_argon2id(db_client: TestClient, owner_url: str) -> None:
    signup(db_client)
    (row,) = run_sql(owner_url, "SELECT password_hash FROM users")
    assert row.password_hash.startswith("$argon2id$")


def test_session_cookies_are_httponly(db_client: TestClient) -> None:
    response = db_client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": "ABC Heating",
            "full_name": "Owner",
            "email": "o@abc.example.com",
            "password": PASSWORD,
        },
    )
    cookies = response.headers.get_list("set-cookie")
    assert any(c.startswith("access_token=") and "HttpOnly" in c for c in cookies)
    assert any(
        c.startswith("refresh_token=") and "HttpOnly" in c and "Path=/api/v1/auth" in c
        for c in cookies
    )


def test_duplicate_email_is_rejected_case_insensitively(db_client: TestClient) -> None:
    signup(db_client, email="owner@abc.example.com")
    response = db_client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": "Other Co",
            "full_name": "X",
            "email": "OWNER@abc.example.com",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


def test_weak_password_rejected_without_echoing_it(db_client: TestClient) -> None:
    response = db_client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": "ABC",
            "full_name": "X",
            "email": "a@b.example.com",
            "password": "short",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "short" not in response.text.replace("string_too_short", "")


def test_login_success_and_failure(db_client: TestClient) -> None:
    signup(db_client, email="owner@abc.example.com")
    db_client.cookies.clear()
    assert login(db_client, "owner@abc.example.com", "wrong password!!") == 401
    assert login(db_client, "nobody@abc.example.com") == 401
    assert login(db_client, "Owner@ABC.Example.com") == 200
    assert db_client.get("/api/v1/me").status_code == 200


def test_unknown_email_and_wrong_password_look_identical(db_client: TestClient) -> None:
    signup(db_client, email="owner@abc.example.com")
    a = db_client.post(
        "/api/v1/auth/login", json={"email": "owner@abc.example.com", "password": "nope"}
    )
    b = db_client.post(
        "/api/v1/auth/login", json={"email": "ghost@abc.example.com", "password": "nope"}
    )
    assert a.status_code == b.status_code == 401
    assert a.json()["error"]["message"] == b.json()["error"]["message"]


def test_account_locks_after_repeated_failures(db_client: TestClient, owner_url: str) -> None:
    signup(db_client, email="owner@abc.example.com")
    db_client.cookies.clear()
    for _ in range(5):
        assert login(db_client, "owner@abc.example.com", "wrong password!!") == 401
    # Even the right password is refused while locked.
    assert login(db_client, "owner@abc.example.com") == 429
    (row,) = run_sql(owner_url, "SELECT locked_until IS NOT NULL AS locked FROM users")
    assert row.locked


def test_me_requires_login(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_tampered_token_rejected(db_client: TestClient) -> None:
    signup(db_client)
    token = db_client.cookies["access_token"]
    db_client.cookies.set("access_token", token[:-4] + "AAAA")
    assert db_client.get("/api/v1/me").status_code == 401


def test_token_signed_with_other_key_rejected(db_settings: Settings) -> None:
    with TestClient(create_app(db_settings)) as real:
        signup(real)
        stolen = real.cookies["access_token"]
    other = db_settings.model_copy(update={"secret_key": SecretStr("x" * 48)})
    with TestClient(create_app(other)) as forged:
        forged.cookies.set("access_token", stolen)
        assert forged.get("/api/v1/me").status_code == 401


def test_refresh_rotates_and_detects_reuse(db_client: TestClient) -> None:
    signup(db_client)
    old_refresh = db_client.cookies.get("refresh_token", path="/api/v1/auth")
    assert old_refresh
    assert db_client.post("/api/v1/auth/refresh").status_code == 204
    new_refresh = db_client.cookies.get("refresh_token", path="/api/v1/auth")
    assert new_refresh and new_refresh != old_refresh
    assert db_client.get("/api/v1/me").status_code == 200

    # Replaying the old refresh token (e.g. stolen) revokes the whole session.
    db_client.cookies.set("refresh_token", old_refresh, path="/api/v1/auth")
    assert db_client.post("/api/v1/auth/refresh").status_code == 401
    db_client.cookies.set("refresh_token", new_refresh, path="/api/v1/auth")
    assert db_client.post("/api/v1/auth/refresh").status_code == 401


def test_logout_revokes_session_immediately(db_client: TestClient) -> None:
    signup(db_client)
    access = db_client.cookies["access_token"]
    assert db_client.post("/api/v1/auth/logout").status_code == 204
    # Even a copy of the still-unexpired access token no longer works.
    db_client.cookies.set("access_token", access)
    assert db_client.get("/api/v1/me").status_code == 401


def test_cross_origin_state_change_blocked(db_client: TestClient) -> None:
    response = db_client.post(
        "/api/v1/auth/login",
        json={"email": "a@b.example.com", "password": "x"},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_signup_can_be_disabled(db_settings: Settings) -> None:
    closed = db_settings.model_copy(update={"allow_public_signup": False})
    with TestClient(create_app(closed)) as c:
        response = c.post(
            "/api/v1/auth/signup",
            json={
                "company_name": "ABC",
                "full_name": "X",
                "email": "a@b.example.com",
                "password": PASSWORD,
            },
        )
        assert response.status_code == 403


def test_readiness_checks_database(db_client: TestClient) -> None:
    assert db_client.get("/health/ready").json() == {"status": "ok", "database": "ok"}
