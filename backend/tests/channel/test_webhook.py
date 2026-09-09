"""Webhook endpoints (Task 7). Unit tests — no emulator, no network.

`handle_inbound` and `get_db` are monkeypatched at the point `webhook.py`
imports them, same convention as `media/test_urls.py`. Inbound-message
orchestration has its own coverage in `test_handle.py` — this file covers
the secret check and the delivery-receipt / auto-close flow that lives in
`webhook.py` itself.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from support_service.channel import webhook as webhook_module
from support_service.main import app
from support_service.models import EventType, ProviderStatus, TicketStatus

TICKET_ID = "TKT-20260909-0001"
WA_NUMBER = "919876543210"


@pytest.fixture(autouse=True)
def _no_webhook_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(webhook_module, "handle_inbound", MagicMock())
    return TestClient(app)


@pytest.fixture
def mock_db(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    db = MagicMock()
    registry: dict[str, MagicMock] = {}
    db.collection.side_effect = lambda name: registry.setdefault(name, MagicMock())
    monkeypatch.setattr(webhook_module, "get_db", lambda: db)
    return db


def _message_doc(**data: object) -> MagicMock:
    doc = MagicMock()
    doc.to_dict.return_value = data
    return doc


def _seed_message_query(mock_db: MagicMock, doc: MagicMock) -> None:
    query = mock_db.collection_group.return_value.where.return_value.limit.return_value
    query.get.return_value = [doc]


def _status_event(event_type: str, gs_id: str = "gs-1") -> dict[str, object]:
    return {"type": "message-event", "payload": {"type": event_type, "gsId": gs_id}}


class TestSecretCheck:
    def test_wrong_secret_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WEBHOOK_SECRET", "correct-secret")
        client = TestClient(app)

        response = client.post(
            "/webhook/gupshup", json={"type": "message"}, params={"secret": "wrong"}
        )

        assert response.status_code == 401


class TestInboundDispatch:
    def test_non_message_events_are_ignored(self, client: TestClient) -> None:
        response = client.post("/webhook/gupshup", json={"type": "message-event"})

        assert response.status_code == 200
        webhook_module.handle_inbound.assert_not_called()

    def test_messages_are_handed_to_the_orchestrator(self, client: TestClient) -> None:
        body = {"type": "message", "payload": {"id": "wamid.1"}}

        response = client.post("/webhook/gupshup", json=body)

        assert response.status_code == 200
        webhook_module.handle_inbound.assert_called_once_with(body)


class TestReceiptStatusUpdate:
    def test_non_status_events_are_ignored(self, client: TestClient, mock_db: MagicMock) -> None:
        response = client.post("/webhook/gupshup/status", json={"type": "message"})

        assert response.status_code == 200
        mock_db.collection_group.assert_not_called()

    def test_unmapped_event_type_is_ignored(self, client: TestClient, mock_db: MagicMock) -> None:
        response = client.post("/webhook/gupshup/status", json=_status_event("weird"))

        assert response.status_code == 200
        mock_db.collection_group.assert_not_called()

    def test_updates_provider_status_on_the_message(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        doc = _message_doc(ticketId=None)
        _seed_message_query(mock_db, doc)

        response = client.post("/webhook/gupshup/status", json=_status_event("sent", "gs-1"))

        assert response.status_code == 200
        mock_db.collection_group.assert_called_with("messages")
        mock_db.collection_group.return_value.where.assert_called_with("messageId", "==", "gs-1")
        doc.reference.update.assert_called_once_with({"providerStatus": ProviderStatus.SENT.value})


class TestDeliveryAutoClose:
    def _seed_message(self, mock_db: MagicMock, ticket_id: str | None) -> MagicMock:
        doc = _message_doc(ticketId=ticket_id)
        _seed_message_query(mock_db, doc)
        return doc

    def test_delivery_without_a_ticket_id_does_not_touch_tickets(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        self._seed_message(mock_db, ticket_id=None)

        response = client.post("/webhook/gupshup/status", json=_status_event("delivered"))

        assert response.status_code == 200
        mock_db.collection("tickets").document.assert_not_called()

    def test_delivery_on_a_ticket_that_is_not_resolved_is_left_alone(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        self._seed_message(mock_db, ticket_id=TICKET_ID)
        ticket_snapshot = MagicMock()
        ticket_snapshot.exists = True
        ticket_snapshot.to_dict.return_value = {"status": TicketStatus.OPEN.value}
        mock_db.collection("tickets").document.return_value.get.return_value = ticket_snapshot

        response = client.post("/webhook/gupshup/status", json=_status_event("delivered"))

        assert response.status_code == 200
        mock_db.collection("tickets").document.return_value.update.assert_not_called()

    def test_delivery_on_a_resolved_ticket_closes_it_and_updates_the_contact(
        self, client: TestClient, mock_db: MagicMock
    ) -> None:
        self._seed_message(mock_db, ticket_id=TICKET_ID)
        ticket_snapshot = MagicMock()
        ticket_snapshot.exists = True
        ticket_snapshot.to_dict.return_value = {
            "status": TicketStatus.RESOLVED.value,
            "waNumber": WA_NUMBER,
            "serviceId": "anganwadi-vr",
        }
        mock_db.collection("tickets").document.return_value.get.return_value = ticket_snapshot

        contact_snapshot = MagicMock()
        contact_snapshot.exists = True
        contact_snapshot.to_dict.return_value = {
            "openTicketIds": [TICKET_ID, "TKT-other"],
            "recentlyClosed": [],
        }
        mock_db.collection("contacts").document.return_value.get.return_value = contact_snapshot

        response = client.post("/webhook/gupshup/status", json=_status_event("delivered"))

        assert response.status_code == 200

        ticket_ref = mock_db.collection("tickets").document.return_value
        ticket_update = ticket_ref.update.call_args.args[0]
        assert ticket_update["status"] == TicketStatus.CLOSED
        assert ticket_update["closedAt"] is not None

        event_data = ticket_ref.collection.return_value.document.return_value.set.call_args.args[0]
        assert event_data["type"] == EventType.DELIVERED
        assert event_data["from"] == TicketStatus.RESOLVED
        assert event_data["to"] == TicketStatus.CLOSED

        contact_ref = mock_db.collection("contacts").document.return_value
        contact_update = contact_ref.update.call_args.args[0]
        assert contact_update["openTicketIds"] == ["TKT-other"]
        assert contact_update["recentlyClosed"][0]["ticketId"] == TICKET_ID
