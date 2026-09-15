"""Cloud Tasks callbacks — unit. The services they dispatch to are faked."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from support_service.controllers import tasks_controller as tasks_module
from support_service.main import app
from support_service.models import SlaState
from support_service.services.media_service import MediaNotReady

SECRET = "test-tasks-secret"
WA = "919876500001"
MSG = "wamid.abc"
MEDIA_BODY = {"wa_number": WA, "message_id": MSG}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    return TestClient(app)


class TestSecret:
    @pytest.mark.parametrize("headers", [{}, {"X-Tasks-Secret": "wrong"}])
    def test_rejected_without_the_right_secret(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, headers: dict[str, str]
    ) -> None:
        fetch = MagicMock()
        monkeypatch.setattr(tasks_module, "fetch_attachment", fetch)

        response = client.post("/tasks/media", json=MEDIA_BODY, headers=headers)

        assert response.status_code == 401
        fetch.assert_not_called()

    def test_no_secret_configured_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("WEBHOOK_SECRET", raising=False)

        response = TestClient(app).post(
            "/tasks/sla", json={"ticket_id": "TKT-1"}, headers={"X-Tasks-Secret": ""}
        )

        assert response.status_code == 401


class TestDispatch:
    def test_media_reports_the_final_state(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fetch = MagicMock(return_value="stored")
        monkeypatch.setattr(tasks_module, "fetch_attachment", fetch)

        response = client.post("/tasks/media", json=MEDIA_BODY, headers={"X-Tasks-Secret": SECRET})

        assert response.status_code == 200
        assert response.json() == {"state": "stored"}
        fetch.assert_called_once_with(WA, MSG)

    def test_media_not_ready_asks_cloud_tasks_to_retry(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            tasks_module, "fetch_attachment", MagicMock(side_effect=MediaNotReady(MSG))
        )

        response = client.post("/tasks/media", json=MEDIA_BODY, headers={"X-Tasks-Secret": SECRET})

        assert response.status_code == 503

    def test_idle(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        finish = MagicMock(return_value="TKT-1")
        monkeypatch.setattr(tasks_module, "finish_idle_session", finish)

        response = client.post(
            "/tasks/idle", json={"wa_number": WA}, headers={"X-Tasks-Secret": SECRET}
        )

        assert response.json() == {"ticket_id": "TKT-1"}
        finish.assert_called_once_with(WA)

    def test_sla(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        check = MagicMock(return_value=SlaState.BREACHED)
        monkeypatch.setattr(tasks_module, "check_sla", check)

        response = client.post(
            "/tasks/sla", json={"ticket_id": "TKT-1"}, headers={"X-Tasks-Secret": SECRET}
        )

        assert response.json() == {"sla_state": "breached"}
        check.assert_called_once_with("TKT-1")
