"""finish_idle_session — unit, no emulator. Runs as a delayed Cloud Task."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from support_service.config import defaults
from support_service.config.defaults import seed
from support_service.conversation.steps import Draft, SendTemplate
from support_service.models import Language
from support_service.services import channel_service as handle_module
from support_service.services.channel_service import finish_idle_session

WA = "919876500001"
IDLE = timedelta(seconds=seed().settings.media_idle_seconds)


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    database = MagicMock()
    monkeypatch.setattr(handle_module, "get_db", lambda: database)
    messages = database.collection.return_value.document.return_value.collection.return_value
    messages.where.return_value.get.return_value = []
    return database


@pytest.fixture
def create(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(return_value="TKT-20260916-0003")
    monkeypatch.setattr(handle_module, "create_ticket", mock)
    return mock


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(return_value="gs-1")
    monkeypatch.setattr(handle_module, "send_reply", mock)
    return mock


def _contact_with(db: MagicMock, session: dict[str, object] | None) -> MagicMock:
    ref = db.collection.return_value.document.return_value
    ref.get.return_value.exists = True
    ref.get.return_value.to_dict.return_value = {"waNumber": WA, "session": session}
    return ref


def _session(*, idle_for: timedelta, **draft: str) -> dict:
    at = datetime.now(UTC) - idle_for
    return {
        "flow": "report",
        "step": "media",
        "draft": {"language": "en", "categoryId": "device", **draft},
        "startedAt": at,
        "lastActivityAt": at,
    }


def test_a_contact_who_never_sent_a_photo_still_gets_a_ticket(
    db: MagicMock, create: MagicMock, sent: MagicMock
) -> None:
    _contact_with(db, _session(idle_for=IDLE + timedelta(seconds=10)))

    assert finish_idle_session(WA) == "TKT-20260916-0003"

    draft, wa_number = create.call_args.args
    assert wa_number == WA
    assert draft == Draft(language=Language.EN, category_id="device", description="")

    confirmation = sent.call_args.args[1]
    assert isinstance(confirmation, SendTemplate)
    assert confirmation.name == defaults.TICKET_CREATED
    assert confirmation.params == ("TKT-20260916-0003", "Device", f"+{WA}")


def test_a_typed_description_is_kept(db: MagicMock, create: MagicMock, sent: MagicMock) -> None:
    _contact_with(db, _session(idle_for=IDLE * 2, description="headset dead"))

    finish_idle_session(WA)

    assert create.call_args.args[0].description == "headset dead"


def test_contact_still_typing_is_left_alone(db: MagicMock, create: MagicMock) -> None:
    ref = _contact_with(db, _session(idle_for=timedelta(seconds=5)))

    assert finish_idle_session(WA) is None

    create.assert_not_called()
    ref.update.assert_not_called()


def test_no_session_means_the_flow_already_finished(db: MagicMock, create: MagicMock) -> None:
    _contact_with(db, None)

    assert finish_idle_session(WA) is None
    create.assert_not_called()


def test_without_a_category_there_is_nothing_to_file(db: MagicMock, create: MagicMock) -> None:
    session = _session(idle_for=IDLE * 2)
    session["draft"] = {"language": "en"}
    ref = _contact_with(db, session)

    assert finish_idle_session(WA) is None

    create.assert_not_called()
    assert ref.update.call_args.args[0]["session"] is None
