from fastapi.testclient import TestClient

from app.api.routes import health
from app.main import app
from app.schemas.health import DatabaseHealth


def test_health_check_reports_api_and_database_status(monkeypatch: object) -> None:
    monkeypatch.setattr(health, "database_status", lambda: DatabaseHealth(status="connected"))  # type: ignore[attr-defined]

    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"]["status"] == "connected"


def test_openapi_document_is_available() -> None:
    response = TestClient(app).get("/openapi.json")

    assert response.status_code == 200
    assert "/api/v1/health" in response.json()["paths"]
