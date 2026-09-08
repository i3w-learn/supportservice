"""Unit — no emulator, no network."""

from fastapi.testclient import TestClient

from support_service.main import app


def test_healthz() -> None:
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
