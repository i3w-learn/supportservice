"""Ticket creation — needs the emulator because it runs as a transaction (§8).

Skipped offline by the guard in conftest.py, same as test_firestore's siblings.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from support_service.conversation.steps import Draft
from support_service.models import Language, TicketStatus
from support_service.repositories.base import get_db
from support_service.services.ticket_service import create_ticket

WA_NUMBER = "919876500001"
COUNTER_DATE = "20260916"
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def _draft(**overrides: object) -> Draft:
    fields: dict[str, object] = {
        "language": Language.EN,
        "category_id": "device",
        "description": "No power since morning",
    }
    fields.update(overrides)
    return Draft(**fields)  # type: ignore[arg-type]


@pytest.fixture
def db():
    database = get_db()
    # The flow never asks for a name, so the ticket copies the WhatsApp one.
    database.collection("contacts").document(WA_NUMBER).set(
        {"waNumber": WA_NUMBER, "displayName": "Asha", "openTicketIds": []}
    )
    yield database
    for collection, doc_id in [("contacts", WA_NUMBER), ("counters", COUNTER_DATE)]:
        database.collection(collection).document(doc_id).delete()
    for ticket in database.collection("tickets").where("waNumber", "==", WA_NUMBER).stream():
        for event in ticket.reference.collection("events").stream():
            event.reference.delete()
        ticket.reference.delete()


@pytest.mark.firestore
def test_creates_an_open_ticket_with_its_category_label(db) -> None:
    ticket_id = create_ticket(_draft(), WA_NUMBER, now=NOW)

    ticket = db.collection("tickets").document(ticket_id).get().to_dict()
    assert ticket["status"] == TicketStatus.OPEN.value
    assert ticket["waNumber"] == WA_NUMBER
    assert ticket["categoryId"] == "device"
    assert ticket["categoryLabel"] == "Device"
    assert ticket["contactName"] == "Asha"

    contact = db.collection("contacts").document(WA_NUMBER).get().to_dict()
    assert contact["openTicketIds"] == [ticket_id]

    events = list(db.collection("tickets").document(ticket_id).collection("events").stream())
    assert len(events) == 1
    assert events[0].to_dict()["type"] == "created"


@pytest.mark.firestore
def test_the_label_is_written_in_the_contact_s_language(db) -> None:
    ticket_id = create_ticket(_draft(language=Language.BN), WA_NUMBER, now=NOW)

    ticket = db.collection("tickets").document(ticket_id).get().to_dict()
    assert ticket["categoryLabel"] == "ডিভাইস"


@pytest.mark.firestore
def test_second_ticket_same_day_gets_next_sequence(db) -> None:
    first_id = create_ticket(_draft(), WA_NUMBER, now=NOW)
    second_id = create_ticket(_draft(category_id="other"), WA_NUMBER, now=NOW)

    assert first_id == "TKT-20260916-0001"
    assert second_id == "TKT-20260916-0002"


@pytest.mark.firestore
def test_a_second_ticket_in_the_same_category_is_allowed(db) -> None:
    """The flow offers "New Ticket" outright, so duplicates are the contact's call."""
    first_id = create_ticket(_draft(), WA_NUMBER, now=NOW)
    second_id = create_ticket(_draft(), WA_NUMBER, now=NOW)

    contact = db.collection("contacts").document(WA_NUMBER).get().to_dict()
    assert contact["openTicketIds"] == [first_id, second_id]


@pytest.mark.firestore
def test_both_deadline_checks_are_scheduled(db, enqueued: MagicMock) -> None:
    ticket_id = create_ticket(_draft(), WA_NUMBER, now=NOW)

    sla = [c for c in enqueued.call_args_list if c.args[0] == "/tasks/sla"]
    assert [c.args[1] for c in sla] == [{"ticket_id": ticket_id}] * 2
