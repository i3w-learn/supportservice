"""Inbound orchestration (Task 7). Unit tests — no emulator, no network.

Firestore (`get_db`) and the routing/step-machine/send functions are
monkeypatched at the point `handle.py` imports them, same convention as
`media/test_urls.py` and `admin_api/test_routes.py`. `route`, `begin` and
`advance` already have their own unit tests (conversation/test_routing.py,
conversation/test_steps.py) — here we only check that `handle_inbound` wires
their outputs to the right Firestore writes and outbound sends.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from support_service.channel import handle as handle_module
from support_service.channel.handle import handle_inbound
from support_service.conversation.routing import (
    AppendToTicket,
    AskAboutRecentlyClosed,
    ContinueSession,
    Disambiguate,
    ReopenTicket,
    StartReport,
)
from support_service.conversation.steps import Draft, Row, SendButtons, SendList, Turn
from support_service.models import (
    ClosedTicketRef,
    EventType,
    Flow,
    Language,
    OpenTicket,
    Session,
    Step,
)

WA_NUMBER = "919876543210"
NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


def _raw_text(message_id: str = "wamid.1", text: str = "Hello") -> dict[str, object]:
    return {
        "app": "TestApp",
        "timestamp": 1725888000000,
        "version": 2,
        "type": "message",
        "payload": {
            "id": message_id,
            "source": WA_NUMBER,
            "type": "text",
            "payload": {"text": text},
            "sender": {"phone": WA_NUMBER, "name": "Test"},
        },
    }


def _fresh_db() -> MagicMock:
    """A Firestore double that keeps one child mock per collection name.

    Plain `MagicMock()` ignores call arguments when memoizing `return_value`,
    so `db.collection("contacts")` and `db.collection("tickets")` would
    otherwise be the *same* object and stomp on each other's configuration.
    """
    db = MagicMock()
    registry: dict[str, MagicMock] = {}
    db.collection.side_effect = lambda name: registry.setdefault(name, MagicMock())
    return db


def _contact_snapshot(**overrides: object) -> MagicMock:
    data: dict[str, object] = {
        "waNumber": WA_NUMBER,
        "displayName": None,
        "centreName": None,
        "language": None,
        "session": None,
        "openTicketIds": [],
        "recentlyClosed": [],
        "lastInboundAt": NOW,
        "lastOutboundAt": None,
        "createdAt": NOW,
        "updatedAt": NOW,
    }
    data.update(overrides)
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = data
    return snapshot


@pytest.fixture
def mock_db(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    db = _fresh_db()
    monkeypatch.setattr(handle_module, "get_db", lambda: db)

    # Not a duplicate by default.
    db.collection("inbound").document.return_value.get.return_value.exists = False

    # An existing, idle contact by default.
    db.collection("contacts").document.return_value.get.return_value = _contact_snapshot()

    # No stray unstamped or outbound-with-ticket messages by default — both
    # query shapes used by handle.py (`.where().get()` and
    # `.where().where().order_by().limit().get()`) must be iterable.
    messages = db.collection("contacts").document.return_value.collection.return_value
    messages.where.return_value.get.return_value = []
    outbound_query = messages.where.return_value.where.return_value.order_by.return_value
    outbound_query.limit.return_value.get.return_value = []

    return db


class TestDedupe:
    def test_duplicate_message_is_ignored(
        self, mock_db: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_db.collection("inbound").document.return_value.get.return_value.exists = True
        route_mock = MagicMock()
        monkeypatch.setattr(handle_module, "route", route_mock)

        handle_inbound(_raw_text())

        route_mock.assert_not_called()
        mock_db.collection("inbound").document.return_value.set.assert_not_called()
        # Nothing about the contact should have been touched either.
        mock_db.collection("contacts").document.return_value.set.assert_not_called()

    def test_first_sighting_is_marked_seen_and_processed(
        self, mock_db: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(handle_module, "route", MagicMock(return_value=StartReport()))
        monkeypatch.setattr(handle_module, "begin", MagicMock(return_value=Turn()))

        handle_inbound(_raw_text(message_id="wamid.new"))

        mock_db.collection("inbound").document.assert_any_call("wamid.new")
        mock_db.collection("inbound").document.return_value.set.assert_called_once()


class TestMessagePersistence:
    def test_appends_inbound_message_and_touches_last_inbound(
        self, mock_db: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(handle_module, "route", MagicMock(return_value=StartReport()))
        monkeypatch.setattr(handle_module, "begin", MagicMock(return_value=Turn()))

        handle_inbound(_raw_text(message_id="wamid.msg-1", text="My headset broke"))

        messages = mock_db.collection("contacts").document.return_value.collection.return_value
        messages.document.assert_any_call("wamid.msg-1")
        stored = messages.document.return_value.set.call_args.args[0]
        assert stored["text"] == "My headset broke"
        assert stored["direction"] == "in"

        contact_doc = mock_db.collection("contacts").document.return_value
        touches = [
            c.args[0] for c in contact_doc.update.call_args_list if "lastInboundAt" in c.args[0]
        ]
        assert len(touches) == 1


class TestContactBootstrap:
    def test_creates_contact_record_for_first_time_sender(
        self, mock_db: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_db.collection("contacts").document.return_value.get.return_value.exists = False
        monkeypatch.setattr(handle_module, "route", MagicMock(return_value=StartReport()))
        monkeypatch.setattr(handle_module, "begin", MagicMock(return_value=Turn()))

        handle_inbound(_raw_text())

        contact_doc = mock_db.collection("contacts").document.return_value
        contact_doc.set.assert_called_once()
        created = contact_doc.set.call_args.args[0]
        assert created["waNumber"] == WA_NUMBER
        assert created["openTicketIds"] == []


class TestClosedTicketIdsComputation:
    def test_excludes_ids_that_are_open_again(
        self, mock_db: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A ticket can be both `openTicketIds` and stale `recentlyClosed` data
        (e.g. reopened by another path) — routing must only see it as closed
        once, so handle.py subtracts the open set before calling `route`."""
        mock_db.collection("contacts").document.return_value.get.return_value = _contact_snapshot(
            openTicketIds=["TKT-2"],
            recentlyClosed=[
                {"ticketId": "TKT-1", "serviceId": "anganwadi-vr", "closedAt": NOW},
                {"ticketId": "TKT-2", "serviceId": "poshan-ai", "closedAt": NOW},
            ],
        )
        ticket_snapshot = MagicMock()
        ticket_snapshot.exists = True
        ticket_snapshot.to_dict.return_value = {
            "serviceId": "poshan-ai",
            "serviceName": "Poshan AI",
        }
        mock_db.collection("tickets").document.return_value.get.return_value = ticket_snapshot

        route_mock = MagicMock(return_value=StartReport())
        monkeypatch.setattr(handle_module, "route", route_mock)
        monkeypatch.setattr(handle_module, "begin", MagicMock(return_value=Turn()))

        handle_inbound(_raw_text())

        assert route_mock.call_args.kwargs["closed_ticket_ids"] == frozenset({"TKT-1"})


class TestStartReportDispatch:
    def test_sends_prompt_and_saves_new_session(
        self, mock_db: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = Session(
            flow=Flow.REPORT, step=Step.LANGUAGE, started_at=NOW, last_activity_at=NOW
        )
        prompt = SendList("Choose your language", (Row("en", "English"),))
        turn = Turn(replies=(prompt,), session=session)

        monkeypatch.setattr(handle_module, "route", MagicMock(return_value=StartReport()))
        monkeypatch.setattr(handle_module, "begin", MagicMock(return_value=turn))
        send_reply_mock = MagicMock(return_value="msg-out-1")
        monkeypatch.setattr(handle_module, "send_reply", send_reply_mock)

        handle_inbound(_raw_text())

        send_reply_mock.assert_called_once_with(WA_NUMBER, prompt)

        contact_doc = mock_db.collection("contacts").document.return_value
        session_updates = [
            c.args[0] for c in contact_doc.update.call_args_list if "session" in c.args[0]
        ]
        assert len(session_updates) == 1
        assert session_updates[0]["session"]["step"] == Step.LANGUAGE.value


class TestContinueSessionDispatch:
    def test_learns_language_and_saves_next_step(
        self, mock_db: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = Session(flow=Flow.REPORT, step=Step.SERVICE, started_at=NOW, last_activity_at=NOW)
        prompt = SendList("Which product?", (Row("anganwadi-vr", "Anganwadi VR"),))
        turn = Turn(replies=(prompt,), session=session, learned_language=Language.HI)

        monkeypatch.setattr(handle_module, "route", MagicMock(return_value=ContinueSession()))
        monkeypatch.setattr(handle_module, "advance", MagicMock(return_value=turn))
        send_reply_mock = MagicMock(return_value="msg-out-2")
        monkeypatch.setattr(handle_module, "send_reply", send_reply_mock)
        create_ticket_mock = MagicMock()
        monkeypatch.setattr(handle_module, "create_ticket", create_ticket_mock)

        handle_inbound(_raw_text())

        create_ticket_mock.assert_not_called()
        send_reply_mock.assert_called_once_with(WA_NUMBER, prompt)

        contact_doc = mock_db.collection("contacts").document.return_value
        language_updates = [
            c.args[0] for c in contact_doc.update.call_args_list if c.args[0] == {"language": "hi"}
        ]
        assert len(language_updates) == 1

    def test_completes_flow_creates_ticket_and_stamps_messages(
        self, mock_db: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        draft = Draft(
            language=Language.EN,
            service_id="anganwadi-vr",
            category_id="headset",
            display_name="Asha",
            centre_name="Ward 4 Centre",
            description="Headset won't turn on",
        )
        turn = Turn(create=draft)

        monkeypatch.setattr(handle_module, "route", MagicMock(return_value=ContinueSession()))
        monkeypatch.setattr(handle_module, "advance", MagicMock(return_value=turn))
        create_ticket_mock = MagicMock(return_value="TKT-20260909-0001")
        monkeypatch.setattr(handle_module, "create_ticket", create_ticket_mock)
        send_text_mock = MagicMock(return_value="msg-out-3")
        monkeypatch.setattr(handle_module, "send_text", send_text_mock)

        unstamped_doc = MagicMock()
        messages = mock_db.collection("contacts").document.return_value.collection.return_value
        messages.where.return_value.get.return_value = [unstamped_doc]

        handle_inbound(_raw_text())

        create_ticket_mock.assert_called_once()
        assert create_ticket_mock.call_args.args == (draft, WA_NUMBER)
        assert isinstance(create_ticket_mock.call_args.kwargs["now"], datetime)

        send_text_mock.assert_called_once()
        sent_wa, sent_text = send_text_mock.call_args.args
        assert sent_wa == WA_NUMBER
        assert "TKT-20260909-0001" in sent_text

        unstamped_doc.reference.update.assert_called_once_with({"ticketId": "TKT-20260909-0001"})

        outbound_data = messages.document.return_value.set.call_args_list[-1].args[0]
        assert outbound_data["ticketId"] == "TKT-20260909-0001"
        assert outbound_data["text"] == sent_text


class TestAppendToTicketDispatch:
    def test_stamps_message_logs_event_and_confirms(
        self, mock_db: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(handle_module, "route", MagicMock(return_value=AppendToTicket("TKT-1")))
        send_text_mock = MagicMock(return_value="msg-out-4")
        monkeypatch.setattr(handle_module, "send_text", send_text_mock)

        handle_inbound(_raw_text(message_id="wamid.append-1", text="still broken"))

        messages = mock_db.collection("contacts").document.return_value.collection.return_value
        messages.document.return_value.update.assert_called_once_with({"ticketId": "TKT-1"})

        events = mock_db.collection("tickets").document.return_value.collection.return_value
        events.document.return_value.set.assert_called_once()
        event_data = events.document.return_value.set.call_args.args[0]
        assert event_data["type"] == EventType.MESSAGE_ADDED

        send_text_mock.assert_called_once()
        sent_wa, sent_text = send_text_mock.call_args.args
        assert sent_wa == WA_NUMBER
        assert "TKT-1" in sent_text


class TestDisambiguateDispatch:
    def test_offers_list_of_open_tickets_plus_new(
        self, mock_db: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        options = (
            OpenTicket(ticket_id="TKT-1", service_id="anganwadi-vr", service_name="Anganwadi VR"),
            OpenTicket(ticket_id="TKT-2", service_id="poshan-ai", service_name="Poshan AI"),
        )
        monkeypatch.setattr(handle_module, "route", MagicMock(return_value=Disambiguate(options)))
        send_reply_mock = MagicMock(return_value="msg-out-5")
        monkeypatch.setattr(handle_module, "send_reply", send_reply_mock)

        handle_inbound(_raw_text())

        expected_rows = (
            Row("anganwadi-vr", "Anganwadi VR"),
            Row("poshan-ai", "Poshan AI"),
            Row("new", "Report a new problem"),
        )
        expected_reply = SendList("Which one is this about?", expected_rows)
        send_reply_mock.assert_called_once_with(WA_NUMBER, expected_reply)


class TestAskAboutRecentlyClosedDispatch:
    def test_asks_before_assuming_same_problem(
        self, mock_db: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        closed = ClosedTicketRef(ticket_id="TKT-9", service_id="anganwadi-vr", closed_at=NOW)
        monkeypatch.setattr(
            handle_module, "route", MagicMock(return_value=AskAboutRecentlyClosed(closed))
        )
        send_reply_mock = MagicMock(return_value="msg-out-6")
        monkeypatch.setattr(handle_module, "send_reply", send_reply_mock)

        handle_inbound(_raw_text())

        expected_text = "Is this about your anganwadi-vr report TKT-9, or a new problem?"
        expected_reply = SendButtons(
            expected_text,
            (Row("reopen", "Same problem"), Row("new", "Report a new problem")),
        )
        send_reply_mock.assert_called_once_with(WA_NUMBER, expected_reply)


class TestReopenTicketDispatch:
    def test_reopens_and_confirms(
        self, mock_db: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(handle_module, "route", MagicMock(return_value=ReopenTicket("TKT-9")))
        reopen_mock = MagicMock()
        monkeypatch.setattr(handle_module, "_reopen", reopen_mock)
        send_text_mock = MagicMock(return_value="msg-out-7")
        monkeypatch.setattr(handle_module, "send_text", send_text_mock)

        handle_inbound(_raw_text())

        reopen_mock.assert_called_once()
        db_arg, ticket_id_arg, wa_arg, _now_arg = reopen_mock.call_args.args
        assert db_arg is mock_db
        assert ticket_id_arg == "TKT-9"
        assert wa_arg == WA_NUMBER

        send_text_mock.assert_called_once()
        sent_wa, sent_text = send_text_mock.call_args.args
        assert sent_wa == WA_NUMBER
        assert "TKT-9" in sent_text
