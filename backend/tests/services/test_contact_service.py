"""Unit — no emulator. `get_db` is monkeypatched with a MagicMock."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from support_service.services import contact_service

WA = "919876500001"


def _doc(**data: object) -> MagicMock:
    doc = MagicMock()
    doc.to_dict.return_value = data
    return doc


def test_purge_deletes_everything_tied_to_the_number(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    registry: dict[str, MagicMock] = {}
    db.collection.side_effect = lambda name: registry.setdefault(name, MagicMock())
    monkeypatch.setattr(contact_service, "get_db", lambda: db)

    contacts, tickets, inbound = (
        db.collection("contacts"),
        db.collection("tickets"),
        db.collection("inbound"),
    )

    inbound_msg = _doc(direction="in", messageId="wamid.1")
    outbound_msg = _doc(direction="out", messageId="gs-1")
    contacts.document.return_value.collection.return_value.get.return_value = [
        inbound_msg,
        outbound_msg,
    ]
    contacts.document.return_value.get.return_value.exists = True

    event = _doc()
    ticket = _doc(waNumber=WA)
    ticket.reference.collection.return_value.get.return_value = [event]
    tickets.where.return_value.get.return_value = [ticket]

    counts = contact_service.purge_contact(WA)

    assert counts == {"messages": 2, "inbound": 1, "tickets": 1, "events": 1, "contact": 1}
    deleted = [call.args[0] for call in db.batch.return_value.delete.call_args_list]
    assert inbound.document.return_value in deleted
    assert inbound_msg.reference in deleted
    assert outbound_msg.reference in deleted
    assert event.reference in deleted
    assert ticket.reference in deleted
    assert contacts.document.return_value in deleted
    assert len(deleted) == 6
    db.batch.return_value.commit.assert_called_once()


def test_purge_of_unknown_number_deletes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    monkeypatch.setattr(contact_service, "get_db", lambda: db)
    db.collection.return_value.document.return_value.collection.return_value.get.return_value = []
    db.collection.return_value.where.return_value.get.return_value = []
    db.collection.return_value.document.return_value.get.return_value.exists = False

    counts = contact_service.purge_contact(WA)

    assert counts == {"messages": 0, "inbound": 0, "tickets": 0, "events": 0, "contact": 0}
    db.batch.assert_not_called()
