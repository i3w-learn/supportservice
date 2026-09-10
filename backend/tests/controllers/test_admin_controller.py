"""Unit — no emulator, no network.

The Firebase auth dependency (`get_admin_uid`) is overridden so these tests
never touch a real token or the `admins` allowlist. Firestore access
(`get_doc`, `update_doc`, `get_db`) and the domain functions it delegates to
(`validate_transition`, `resolve_ticket`) are monkeypatched at the point
`routes.py` imports them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from support_service.controllers import admin_controller as admin_routes
from support_service.main import app
from support_service.models import TicketStatus
from support_service.services import ticket_service as resolution_module
from support_service.services.auth_service import get_admin_uid

ADMIN_UID = "admin-uid-1"
TICKET_ID = "TKT-20260909-0001"


@pytest.fixture
def client():
    app.dependency_overrides[get_admin_uid] = lambda: ADMIN_UID
    yield TestClient(app)
    app.dependency_overrides.pop(get_admin_uid, None)


@pytest.fixture
def mock_db(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    db = MagicMock()
    monkeypatch.setattr(admin_routes, "get_db", lambda: db)
    return db


def _ticket(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "status": TicketStatus.OPEN,
        "wa_number": "919876500001",
        "first_response_at": None,
        "resolution": None,
    }
    base.update(overrides)
    return base


class TestChangeStatus:
    def test_missing_ticket_returns_404(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(admin_routes, "get_doc", lambda *a, **kw: None)

        response = client.patch(f"/tickets/{TICKET_ID}/status", json={"to": "in_progress"})

        assert response.status_code == 404

    def test_illegal_transition_returns_409(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(admin_routes, "get_doc", lambda *a, **kw: _ticket(status="closed"))

        def _raise(*args: object, **kwargs: object) -> None:
            raise ValueError("closed → resolved is not a legal transition")

        monkeypatch.setattr(admin_routes, "validate_transition", _raise)

        response = client.patch(f"/tickets/{TICKET_ID}/status", json={"to": "resolved"})

        assert response.status_code == 409
        assert "not a legal transition" in response.json()["detail"]

    def test_legal_transition_updates_and_logs_event(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        mock_db: MagicMock,
    ) -> None:
        monkeypatch.setattr(admin_routes, "get_doc", lambda *a, **kw: _ticket(status="open"))
        monkeypatch.setattr(admin_routes, "validate_transition", lambda *a, **kw: None)
        update_calls: list[tuple[Any, ...]] = []
        monkeypatch.setattr(
            admin_routes,
            "update_doc",
            lambda *a, **kw: update_calls.append(a),
        )

        response = client.patch(
            f"/tickets/{TICKET_ID}/status", json={"to": "in_progress", "note": "picked up"}
        )

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert len(update_calls) == 1
        collection, doc_id, updates = update_calls[0]
        assert (collection, doc_id) == ("tickets", TICKET_ID)
        assert updates["status"] == "in_progress"
        assert "updated_at" in updates
        assert "first_response_at" in updates  # first response — was None on the ticket
        mock_db.collection.assert_any_call("tickets")


class TestSendResolution:
    def test_success_returns_message_id(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(admin_routes, "resolve_ticket", lambda *a, **kw: "gs-msg-1")

        response = client.post(f"/tickets/{TICKET_ID}/resolution", json={"text": "Fixed it"})

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "messageId": "gs-msg-1"}

    def test_illegal_transition_returns_409(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*args: object, **kwargs: object) -> str:
            raise ValueError("closed → resolved is not a legal transition")

        monkeypatch.setattr(admin_routes, "resolve_ticket", _raise)

        response = client.post(f"/tickets/{TICKET_ID}/resolution", json={"text": "Fixed it"})

        assert response.status_code == 409

    def test_send_failure_returns_502(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*args: object, **kwargs: object) -> str:
            raise RuntimeError("gupshup down")

        monkeypatch.setattr(admin_routes, "resolve_ticket", _raise)

        response = client.post(f"/tickets/{TICKET_ID}/resolution", json={"text": "Fixed it"})

        assert response.status_code == 502


class TestAddNote:
    def test_missing_ticket_returns_404(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(admin_routes, "get_doc", lambda *a, **kw: None)

        response = client.post(f"/tickets/{TICKET_ID}/notes", json={"text": "called back"})

        assert response.status_code == 404

    def test_success_writes_event_and_touches_ticket(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        mock_db: MagicMock,
    ) -> None:
        monkeypatch.setattr(admin_routes, "get_doc", lambda *a, **kw: _ticket())
        update_calls: list[tuple[Any, ...]] = []
        monkeypatch.setattr(
            admin_routes,
            "update_doc",
            lambda *a, **kw: update_calls.append(a),
        )

        response = client.post(f"/tickets/{TICKET_ID}/notes", json={"text": "called back"})

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert len(update_calls) == 1
        assert update_calls[0][0] == "tickets"
        assert update_calls[0][1] == TICKET_ID
        mock_db.collection.assert_any_call("tickets")


class TestResendResolution:
    def test_missing_ticket_returns_404(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(admin_routes, "get_doc", lambda *a, **kw: None)

        response = client.post(f"/tickets/{TICKET_ID}/resend")

        assert response.status_code == 404

    def test_no_resolution_returns_409(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            admin_routes, "get_doc", lambda *a, **kw: _ticket(status="open", resolution=None)
        )

        response = client.post(f"/tickets/{TICKET_ID}/resend")

        assert response.status_code == 409
        assert response.json()["detail"] == "Nothing to resend"

    def test_delivery_did_not_fail_returns_409(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ticket = _ticket(
            status=TicketStatus.RESOLVED,
            resolution={"text": "Fixed it", "delivery_state": "delivered"},
        )
        monkeypatch.setattr(admin_routes, "get_doc", lambda *a, **kw: ticket)

        response = client.post(f"/tickets/{TICKET_ID}/resend")

        assert response.status_code == 409
        assert response.json()["detail"] == "Delivery did not fail"

    def test_success_resends_via_real_function(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exercises the real `resend_resolution` (tickets/resolution.py), not
        a mock standing in for it — this is what would have caught the
        RESOLVED -> RESOLVED validate_transition bug: a mocked-away
        `resolve_ticket` always returns 200 regardless of what the real
        function does.
        """
        wa_number = "919876500001"
        ticket = _ticket(
            status=TicketStatus.RESOLVED,
            wa_number=wa_number,
            resolution={"text": "Fixed it", "delivery_state": "failed", "attempts": 1},
        )
        contact = {"last_inbound_at": datetime.now(UTC)}  # inside the 24h window

        def _get_doc(collection: str, doc_id: str) -> dict[str, Any] | None:
            if collection == "tickets":
                return ticket
            if collection == "contacts":
                return contact
            raise AssertionError(f"unexpected collection {collection}")

        # `admin_routes.get_doc` gates the endpoint's own 404/409 checks;
        # `resolution_module.get_doc` is what the real resend_resolution
        # uses internally when it re-reads the ticket and contact.
        monkeypatch.setattr(admin_routes, "get_doc", _get_doc)
        monkeypatch.setattr(resolution_module, "get_doc", _get_doc)

        mock_db = MagicMock()
        monkeypatch.setattr(resolution_module, "get_db", lambda: mock_db)

        sent: dict[str, str] = {}

        def _send_text(to: str, text: str) -> str:
            sent["to"] = to
            sent["text"] = text
            return "gs-msg-2"

        monkeypatch.setattr(resolution_module, "send_text", _send_text)

        response = client.post(f"/tickets/{TICKET_ID}/resend")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "messageId": "gs-msg-2"}
        assert sent == {"to": wa_number, "text": "Fixed it"}

        # No status-transition attempt: the fix's whole point is that this
        # path never calls validate_transition(RESOLVED, RESOLVED). Instead
        # it writes the resolution straight back to "queued" with attempts
        # incremented.
        ticket_ref = mock_db.collection.return_value.document.return_value
        ticket_ref.update.assert_called_once()
        (updates,) = ticket_ref.update.call_args.args
        assert updates["resolution"]["deliveryState"] == "queued"
        assert updates["resolution"]["attempts"] == 2
        ticket_ref.collection.return_value.document.return_value.set.assert_called_once()


class TestAttachmentUrl:
    """Mounted at /attachments, not /tickets/attachments — matches the
    dashboard's api.getAttachmentUrl(), which calls the bare path."""

    def test_found_returns_url(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            admin_routes, "get_signed_url", lambda message_id: "https://signed.example"
        )

        response = client.get("/attachments/wamid.abc/url")

        assert response.status_code == 200
        assert response.json() == {"url": "https://signed.example"}

    def test_missing_returns_404(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(admin_routes, "get_signed_url", lambda message_id: None)

        response = client.get("/attachments/wamid.abc/url")

        assert response.status_code == 404


class TestAuth:
    def test_missing_token_returns_401(self) -> None:
        response = TestClient(app).patch(f"/tickets/{TICKET_ID}/status", json={"to": "in_progress"})

        assert response.status_code == 401

    def test_missing_token_returns_401_for_attachment_url(self) -> None:
        response = TestClient(app).get("/attachments/wamid.abc/url")

        assert response.status_code == 401
