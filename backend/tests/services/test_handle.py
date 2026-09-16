"""Inbound orchestration. Unit tests — no emulator, no network.

Firestore (`get_db`) and the outbound send are monkeypatched at the point
`channel_service` imports them; routing and the step machine run for real, so
these tests check the wiring between them and Firestore.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from support_service.config import defaults
from support_service.config.defaults import seed
from support_service.conversation.steps import Draft, SendTemplate
from support_service.models import Language
from support_service.services import channel_service as handle_module
from support_service.services.channel_service import handle_inbound

WA_NUMBER = "919876543210"
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def _raw(payload: dict[str, object]) -> dict[str, object]:
    return {
        "app": "TestApp",
        "timestamp": 1758024000000,
        "version": 2,
        "type": "message",
        "payload": {
            "source": WA_NUMBER,
            "sender": {"phone": WA_NUMBER, "name": "Sunita Devi"},
            **payload,
        },
    }


def _raw_text(message_id: str = "wamid.1", text: str = "Hi") -> dict[str, object]:
    return _raw({"id": message_id, "type": "text", "payload": {"text": text}})


def _raw_tap(title: str, message_id: str = "wamid.tap") -> dict[str, object]:
    return _raw({"id": message_id, "type": "button_reply", "payload": {"title": title, "id": "0"}})


def _raw_image(message_id: str = "wamid.img") -> dict[str, object]:
    return _raw(
        {
            "id": message_id,
            "type": "image",
            "payload": {
                "url": "https://filemanager.gupshup.io/fm/wamedia/TestApp/img-1",
                "contentType": "image/jpeg",
            },
        }
    )


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
        "displayName": "Sunita Devi",
        "language": None,
        "session": None,
        "openTicketIds": [],
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


def _session(step: str, **draft: str) -> dict[str, object]:
    return {
        "flow": "report",
        "step": step,
        "draft": draft,
        "startedAt": datetime.now(UTC),
        "lastActivityAt": datetime.now(UTC),
    }


@pytest.fixture
def mock_db(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    db = _fresh_db()
    monkeypatch.setattr(handle_module, "get_db", lambda: db)

    # Not a duplicate by default.
    db.collection("inbound").document.return_value.get.return_value.exists = False

    # An existing, idle contact by default.
    db.collection("contacts").document.return_value.get.return_value = _contact_snapshot()

    # No stray unstamped messages.
    messages = db.collection("contacts").document.return_value.collection.return_value
    messages.where.return_value.get.return_value = []

    return db


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(return_value="gs-out-1")
    monkeypatch.setattr(handle_module, "send_reply", mock)
    return mock


def _templates(sent: MagicMock) -> list[SendTemplate]:
    return [c.args[1] for c in sent.call_args_list if isinstance(c.args[1], SendTemplate)]


def _session_updates(mock_db: MagicMock) -> list[dict]:
    contact_doc = mock_db.collection("contacts").document.return_value
    return [
        c.args[0]["session"] for c in contact_doc.update.call_args_list if "session" in c.args[0]
    ]


def _open_ticket(mock_db: MagicMock, ticket_id: str = "TKT-20260916-0042") -> None:
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = {
        "categoryId": "software",
        "categoryLabel": "Software",
        "status": "in_progress",
        "createdAt": NOW - timedelta(days=1),
    }
    mock_db.collection("tickets").document.return_value.get.return_value = snapshot
    mock_db.collection("contacts").document.return_value.get.return_value = _contact_snapshot(
        language="en", openTicketIds=[ticket_id]
    )


class TestDedupe:
    def test_duplicate_message_is_ignored(self, mock_db: MagicMock, sent: MagicMock) -> None:
        mock_db.collection("inbound").document.return_value.get.return_value.exists = True

        handle_inbound(_raw_text())

        sent.assert_not_called()
        mock_db.collection("contacts").document.return_value.set.assert_not_called()

    def test_first_sighting_is_marked_seen(self, mock_db: MagicMock, sent: MagicMock) -> None:
        handle_inbound(_raw_text(message_id="wamid.new"))

        mock_db.collection("inbound").document.assert_any_call("wamid.new")
        mock_db.collection("inbound").document.return_value.set.assert_called_once()


class TestMessagePersistence:
    def test_appends_inbound_message_and_touches_last_inbound(
        self, mock_db: MagicMock, sent: MagicMock
    ) -> None:
        handle_inbound(_raw_text(message_id="wamid.msg-1", text="My headset broke"))

        messages = mock_db.collection("contacts").document.return_value.collection.return_value
        messages.document.assert_any_call("wamid.msg-1")
        # The first write is the inbound message; later ones are what we sent back.
        stored = messages.document.return_value.set.call_args_list[0].args[0]
        assert stored["text"] == "My headset broke"
        assert stored["direction"] == "in"

        contact_doc = mock_db.collection("contacts").document.return_value
        touches = [
            c.args[0] for c in contact_doc.update.call_args_list if "lastInboundAt" in c.args[0]
        ]
        assert len(touches) == 1


class TestContactBootstrap:
    def test_first_time_sender_is_created_with_their_whatsapp_name(
        self, mock_db: MagicMock, sent: MagicMock
    ) -> None:
        mock_db.collection("contacts").document.return_value.get.return_value.exists = False

        handle_inbound(_raw_text())

        contact_doc = mock_db.collection("contacts").document.return_value
        created = contact_doc.set.call_args.args[0]
        assert created["waNumber"] == WA_NUMBER
        assert created["displayName"] == "Sunita Devi", "the flow never asks for a name"
        assert created["openTicketIds"] == []

    def test_a_missing_name_is_filled_in_later(self, mock_db: MagicMock, sent: MagicMock) -> None:
        mock_db.collection("contacts").document.return_value.get.return_value = _contact_snapshot(
            displayName=None
        )

        handle_inbound(_raw_text())

        contact_doc = mock_db.collection("contacts").document.return_value
        assert {"displayName": "Sunita Devi"} in [
            c.args[0] for c in contact_doc.update.call_args_list
        ]


class TestDispatch:
    def test_a_first_message_asks_for_a_language(self, mock_db: MagicMock, sent: MagicMock) -> None:
        handle_inbound(_raw_text())

        assert [t.name for t in _templates(sent)] == [defaults.WELCOME_LANGUAGE]
        assert _session_updates(mock_db)[0]["step"] == "language"

    def test_an_open_ticket_offers_the_choice_instead(
        self, mock_db: MagicMock, sent: MagicMock
    ) -> None:
        _open_ticket(mock_db)

        handle_inbound(_raw_text())

        template = _templates(sent)[0]
        assert template.name == defaults.RETURNING_OPTIONS
        assert template.params == ("TKT-20260916-0042",)
        assert _session_updates(mock_db)[0]["step"] == "returning"

    def test_a_running_flow_answers_the_step_it_is_on(
        self, mock_db: MagicMock, sent: MagicMock
    ) -> None:
        mock_db.collection("contacts").document.return_value.get.return_value = _contact_snapshot(
            language="en", session=_session("category", language="en")
        )

        handle_inbound(_raw_tap("Device"))

        template = _templates(sent)[0]
        assert template.name == defaults.UPLOAD_MEDIA
        assert template.params == ("Device",)
        assert _session_updates(mock_db)[0]["step"] == "media"

    def test_a_learned_language_is_saved_on_the_contact(
        self, mock_db: MagicMock, sent: MagicMock
    ) -> None:
        mock_db.collection("contacts").document.return_value.get.return_value = _contact_snapshot(
            session=_session("language")
        )

        handle_inbound(_raw_tap("हिन्दी"))

        contact_doc = mock_db.collection("contacts").document.return_value
        assert {"language": "hi"} in [c.args[0] for c in contact_doc.update.call_args_list]

    def test_an_answered_question_ends_the_flow(self, mock_db: MagicMock, sent: MagicMock) -> None:
        """ "Previous Ticket" replies with the status and leaves nothing open."""
        _open_ticket(mock_db, "TKT-1")
        mock_db.collection("contacts").document.return_value.get.return_value = _contact_snapshot(
            language="en",
            openTicketIds=["TKT-1"],
            session=_session(
                "returning",
                language="en",
                ticket_id="TKT-1",
                category_label="Software",
                status="in_progress",
                raised_on="14 Sep 2026",
            ),
        )

        handle_inbound(_raw_tap("Previous Ticket"))

        assert _templates(sent)[0].name == defaults.TICKET_STATUS
        assert _session_updates(mock_db) == [None]


class TestCompletion:
    @pytest.fixture
    def created(self, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
        mock = MagicMock(return_value="TKT-20260916-0007")
        monkeypatch.setattr(handle_module, "create_ticket", mock)
        return mock

    def test_a_photo_files_the_ticket_and_confirms_it(
        self, mock_db: MagicMock, sent: MagicMock, created: MagicMock
    ) -> None:
        mock_db.collection("contacts").document.return_value.get.return_value = _contact_snapshot(
            language="en", session=_session("media", language="en", category_id="device")
        )
        unstamped = MagicMock()
        messages = mock_db.collection("contacts").document.return_value.collection.return_value
        messages.where.return_value.get.return_value = [unstamped]

        handle_inbound(_raw_image())

        draft, wa_number = created.call_args.args
        assert wa_number == WA_NUMBER
        assert draft == Draft(language=Language.EN, category_id="device", description="")

        template = _templates(sent)[0]
        assert template.name == defaults.TICKET_CREATED
        assert template.params == ("TKT-20260916-0007", "Device", f"+{WA_NUMBER}")

        unstamped.reference.update.assert_called_once_with({"ticketId": "TKT-20260916-0007"})


class TestBackgroundWork:
    def test_attachment_queues_a_download(
        self, mock_db: MagicMock, sent: MagicMock, enqueued: MagicMock
    ) -> None:
        handle_inbound(_raw_image("wamid.img"))

        assert (
            "/tasks/media",
            {"wa_number": WA_NUMBER, "message_id": "wamid.img"},
        ) in [c.args for c in enqueued.call_args_list]

    def test_text_message_queues_nothing(
        self, mock_db: MagicMock, sent: MagicMock, enqueued: MagicMock
    ) -> None:
        handle_inbound(_raw_text())

        enqueued.assert_not_called()

    def test_the_media_step_schedules_an_idle_check(
        self, mock_db: MagicMock, sent: MagicMock, enqueued: MagicMock
    ) -> None:
        mock_db.collection("contacts").document.return_value.get.return_value = _contact_snapshot(
            language="en", session=_session("category", language="en")
        )

        handle_inbound(_raw_tap("Device"))

        idle = [c for c in enqueued.call_args_list if c.args[0] == "/tasks/idle"]
        assert len(idle) == 1
        assert idle[0].args[1] == {"wa_number": WA_NUMBER}
        assert idle[0].kwargs["at"] is not None


class TestStaleSession:
    def _with_session_started(self, mock_db: MagicMock, ago: timedelta) -> None:
        started = datetime.now(UTC) - ago
        session = _session("category", language="en")
        session["startedAt"] = started
        session["lastActivityAt"] = started
        mock_db.collection("contacts").document.return_value.get.return_value = _contact_snapshot(
            language="en", session=session
        )

    def test_an_abandoned_flow_is_dropped_and_the_contact_starts_over(
        self, mock_db: MagicMock, sent: MagicMock
    ) -> None:
        expiry = timedelta(hours=seed().settings.session_expiry_hours)
        self._with_session_started(mock_db, expiry + timedelta(hours=1))

        handle_inbound(_raw_text())

        # The language is known, so starting over means the category question.
        assert _templates(sent)[0].name == defaults.ISSUE_CATEGORY
        assert None in _session_updates(mock_db)

    def test_a_recent_flow_is_kept(self, mock_db: MagicMock, sent: MagicMock) -> None:
        self._with_session_started(mock_db, timedelta(minutes=10))

        handle_inbound(_raw_tap("Device"))

        assert _templates(sent)[0].name == defaults.UPLOAD_MEDIA
