"""Contact administration: wipe everything tied to one WhatsApp number."""

from __future__ import annotations

from typing import Any

from support_service.repositories.base import get_db
from support_service.repositories.contact_repository import contact_messages, contact_ref
from support_service.repositories.ticket_repository import tickets

_BATCH_LIMIT = 400  # Firestore caps a write batch at 500 operations


def purge_contact(wa_number: str) -> dict[str, int]:
    db = get_db()
    refs: list[Any] = []
    counts = {"messages": 0, "inbound": 0, "tickets": 0, "events": 0, "contact": 0}

    for msg in contact_messages(db, wa_number).get():
        data = msg.to_dict() or {}
        if data.get("direction") == "in" and data.get("messageId"):
            refs.append(db.collection("inbound").document(data["messageId"]))
            counts["inbound"] += 1
        refs.append(msg.reference)
        counts["messages"] += 1

    for ticket in tickets(db).where("waNumber", "==", wa_number).get():
        for event in ticket.reference.collection("events").get():
            refs.append(event.reference)
            counts["events"] += 1
        refs.append(ticket.reference)
        counts["tickets"] += 1

    contact = contact_ref(db, wa_number)
    if contact.get().exists:
        refs.append(contact)
        counts["contact"] = 1

    for start in range(0, len(refs), _BATCH_LIMIT):
        batch = db.batch()
        for ref in refs[start : start + _BATCH_LIMIT]:
            batch.delete(ref)
        batch.commit()

    return counts
