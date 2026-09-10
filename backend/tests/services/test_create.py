"""Ticket creation — needs the emulator because it runs as a transaction (§8).

Skipped offline by the guard in conftest.py, same as test_firestore's siblings.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from support_service.conversation.steps import Draft
from support_service.models import Language, TicketStatus
from support_service.repositories.base import get_db
from support_service.services.ticket_service import create_ticket

WA_NUMBER = "919876500001"
SERVICE_ID = "svc-electricity"
CATEGORY_ID = "cat-outage"
COUNTER_DATE = "20260909"


def _draft(**overrides: object) -> Draft:
    fields: dict[str, object] = {
        "language": Language.EN,
        "service_id": SERVICE_ID,
        "category_id": CATEGORY_ID,
        "display_name": "Asha",
        "centre_name": "Ward 4 Centre",
        "description": "No power since morning",
    }
    fields.update(overrides)
    return Draft(**fields)  # type: ignore[arg-type]


@pytest.fixture
def db():
    database = get_db()
    database.collection("services").document(SERVICE_ID).set(
        {
            "name": {"en": "Electricity"},
            "categories": [{"id": CATEGORY_ID, "label": {"en": "Power outage"}}],
        }
    )
    yield database
    for collection, doc_id in [
        ("services", SERVICE_ID),
        ("contacts", WA_NUMBER),
        ("counters", COUNTER_DATE),
    ]:
        database.collection(collection).document(doc_id).delete()
    for ticket in database.collection("tickets").where("waNumber", "==", WA_NUMBER).stream():
        for event in ticket.reference.collection("events").stream():
            event.reference.delete()
        ticket.reference.delete()


@pytest.mark.firestore
def test_creates_ticket_with_open_status_and_resolved_labels(db) -> None:
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)

    ticket_id = create_ticket(_draft(), WA_NUMBER, now=now)

    ticket = db.collection("tickets").document(ticket_id).get().to_dict()
    assert ticket["status"] == TicketStatus.OPEN.value
    assert ticket["waNumber"] == WA_NUMBER
    assert ticket["serviceName"] == "Electricity"
    assert ticket["categoryLabel"] == "Power outage"

    contact = db.collection("contacts").document(WA_NUMBER).get().to_dict()
    assert contact["openTicketIds"] == [ticket_id]

    events = list(db.collection("tickets").document(ticket_id).collection("events").stream())
    assert len(events) == 1
    assert events[0].to_dict()["type"] == "created"


@pytest.mark.firestore
def test_second_ticket_same_day_gets_next_sequence(db) -> None:
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)

    first_id = create_ticket(_draft(), WA_NUMBER, now=now)
    second_id = create_ticket(
        _draft(service_id="svc-water", category_id="cat-other"),
        WA_NUMBER,
        now=now,
    )

    assert first_id == "TKT-20260909-0001"
    assert second_id == "TKT-20260909-0002"

    db.collection("services").document("svc-water").delete()


@pytest.mark.firestore
def test_duplicate_open_ticket_for_same_service_raises(db) -> None:
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)

    create_ticket(_draft(), WA_NUMBER, now=now)

    with pytest.raises(ValueError, match="Already open"):
        create_ticket(_draft(), WA_NUMBER, now=now)
