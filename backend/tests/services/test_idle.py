"""finish_idle_session — unit, no emulator. Runs as a delayed Cloud Task."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from support_service.config.defaults import seed
from support_service.conversation.steps import Draft
from support_service.models import Language
from support_service.services import channel_service as handle_module
from support_service.services.channel_service import finish_idle_session

WA = "919876500001"
IDLE = timedelta(seconds=seed().settings.description_idle_seconds)


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    database = MagicMock()
    monkeypatch.setattr(handle_module, "get_db", lambda: database)
    messages = database.collection.return_value.document.return_value.collection.return_value
    messages.where.return_value.get.return_value = []
    return database


@pytest.fixture
def create(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(return_value="TKT-20260911-0003")
    monkeypatch.setattr(handle_module, "create_ticket", mock)
    return mock


@pytest.fixture
def send(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(return_value="gs-1")
    monkeypatch.setattr(handle_module, "send_text", mock)
    return mock


def _contact_with(db: MagicMock, session: dict[str, object] | None) -> MagicMock:
    ref = db.collection.return_value.document.return_value
    ref.get.return_value.exists = True
    ref.get.return_value.to_dict.return_value = {"waNumber": WA, "session": session}
    return ref


def _session(
    *, idle_for: timedelta, description: str = "Headset won't charge", **extra: str
) -> dict:
    at = datetime.now(UTC) - idle_for
    return {
        "flow": "report",
        "step": "description",
        "draft": {
            "language": "en",
            "serviceId": "anganwadi-vr",
            "categoryId": "headset",
            "displayName": "Asha",
            "centreName": "Ward 4",
            "description": description,
            **extra,
        },
        "startedAt": at,
        "lastActivityAt": at,
    }


def test_idle_description_becomes_a_ticket(
    db: MagicMock, create: MagicMock, send: MagicMock
) -> None:
    _contact_with(db, _session(idle_for=IDLE + timedelta(seconds=10)))

    assert finish_idle_session(WA) == "TKT-20260911-0003"

    draft, wa = create.call_args.args
    assert wa == WA
    assert draft == Draft(
        language=Language.EN,
        service_id="anganwadi-vr",
        category_id="headset",
        display_name="Asha",
        centre_name="Ward 4",
        description="Headset won't charge",
    )
    assert "TKT-20260911-0003" in send.call_args.args[1]


def test_contact_still_typing_is_left_alone(db: MagicMock, create: MagicMock) -> None:
    ref = _contact_with(db, _session(idle_for=timedelta(seconds=5)))

    assert finish_idle_session(WA) is None

    create.assert_not_called()
    ref.update.assert_not_called()


def test_no_session_means_done_was_already_tapped(db: MagicMock, create: MagicMock) -> None:
    _contact_with(db, None)

    assert finish_idle_session(WA) is None
    create.assert_not_called()


def test_nothing_said_closes_the_session_without_a_ticket(db: MagicMock, create: MagicMock) -> None:
    ref = _contact_with(db, _session(idle_for=IDLE * 2, description=""))

    assert finish_idle_session(WA) is None

    create.assert_not_called()
    assert ref.update.call_args.args[0]["session"] is None


def test_photos_alone_become_a_ticket(db: MagicMock, create: MagicMock, send: MagicMock) -> None:
    _contact_with(db, _session(idle_for=IDLE * 2, description="", hasMedia="yes"))

    assert finish_idle_session(WA) == "TKT-20260911-0003"
    assert create.call_args.args[0].description == ""


def test_open_ticket_for_the_same_product_closes_the_session(
    db: MagicMock, create: MagicMock
) -> None:
    ref = _contact_with(db, _session(idle_for=IDLE * 2))
    create.side_effect = ValueError("Already open for this product")

    assert finish_idle_session(WA) is None
    assert ref.update.call_args.args[0]["session"] is None
