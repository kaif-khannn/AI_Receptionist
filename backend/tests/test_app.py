import pytest
from fastapi.testclient import TestClient

from app.core.config import Environment, Settings
from app.main import create_app


def test_liveness(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness(client: TestClient) -> None:
    assert client.get("/health/ready").status_code == 200


def test_request_id_is_generated(client: TestClient) -> None:
    response = client.get("/health/live")
    assert len(response.headers["x-request-id"]) == 32


def test_valid_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/health/live", headers={"x-request-id": "abc-123"})
    assert response.headers["x-request-id"] == "abc-123"


def test_malformed_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health/live", headers={"x-request-id": "bad id\nwith newline"})
    assert response.headers["x-request-id"] != "bad id\nwith newline"


def test_docs_hidden_in_production() -> None:
    settings = Settings(environment=Environment.PRODUCTION, _env_file=None)
    with TestClient(create_app(settings)) as prod_client:
        assert prod_client.get("/docs").status_code == 404
        assert prod_client.get("/openapi.json").status_code == 404


def test_cors_origins_parsed_from_comma_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    assert Settings(_env_file=None).cors_origins == ["http://a.test", "http://b.test"]
