"""Send a resolution and manage the resolved/closed lifecycle (§4.3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from support_service.channel.send import send_template, send_text
from support_service.firestore import get_db, get_doc, to_firestore
from support_service.models import EventType, ProviderStatus, TicketStatus
from support_service.tickets.transitions import validate_transition

TEMPLATE_NAME = "resolution_notification"


def resolve_ticket(ticket_id: str, text: str, actor_uid: str) -> str:
    ticket = get_doc("tickets", ticket_id)
    if not ticket:
        raise ValueError(f"Ticket {ticket_id} not found")

    current = TicketStatus(ticket["status"])
    validate_transition(current, TicketStatus.RESOLVED)

    wa_number = ticket["wa_number"]
    contact = get_doc("contacts", wa_number)
    last_inbound = contact.get("last_inbound_at") if contact else None

    now = datetime.now(UTC)
    window = timedelta(hours=24)
    inside_window = last_inbound and (now - last_inbound) < window

    if inside_window:
        message_id = send_text(wa_number, text)
        sent_via = "freeform"
    else:
        language = ticket.get("language", "en")
        contact_name = ticket.get("contact_name", "")
        params = [contact_name, ticket_id, text]
        message_id = send_template(wa_number, TEMPLATE_NAME, language, params)
        sent_via = "template"

    db = get_db()
    ticket_ref = db.collection("tickets").document(ticket_id)
    ticket_ref.update(
        to_firestore(
            {
                "status": TicketStatus.RESOLVED,
                "resolved_at": now,
                "updated_at": now,
                "resolution": {
                    "text": text,
                    "sent_at": now,
                    "delivery_state": ProviderStatus.QUEUED,
                    "attempts": 1,
                },
            }
        )
    )

    ticket_ref.collection("events").document().set(
        to_firestore(
            {
                "type": EventType.RESOLUTION_SENT,
                "from": current,
                "to": TicketStatus.RESOLVED,
                "actor": "admin",
                "actor_uid": actor_uid,
                "note": f"Sent as {sent_via}",
                "at": now,
            }
        )
    )

    return message_id


def resend_resolution(ticket_id: str, actor_uid: str) -> str:
    """Retry delivery of an already-sent resolution.

    Unlike `resolve_ticket`, this does not run `validate_transition` — the
    ticket is already `resolved`, and `resolved -> resolved` is not a legal
    transition (§8), so reusing `resolve_ticket` here would always 409. This
    is a retry of the send, not a status change.
    """
    ticket = get_doc("tickets", ticket_id)
    if not ticket:
        raise ValueError(f"Ticket {ticket_id} not found")

    current = TicketStatus(ticket["status"])
    if current != TicketStatus.RESOLVED:
        raise ValueError(f"Ticket {ticket_id} is not resolved")

    resolution = ticket.get("resolution")
    if not resolution:
        raise ValueError(f"Ticket {ticket_id} has no resolution to resend")

    text = resolution["text"]
    wa_number = ticket["wa_number"]
    contact = get_doc("contacts", wa_number)
    last_inbound = contact.get("last_inbound_at") if contact else None

    now = datetime.now(UTC)
    window = timedelta(hours=24)
    inside_window = last_inbound and (now - last_inbound) < window

    if inside_window:
        message_id = send_text(wa_number, text)
        sent_via = "freeform"
    else:
        language = ticket.get("language", "en")
        contact_name = ticket.get("contact_name", "")
        params = [contact_name, ticket_id, text]
        message_id = send_template(wa_number, TEMPLATE_NAME, language, params)
        sent_via = "template"

    db = get_db()
    ticket_ref = db.collection("tickets").document(ticket_id)
    ticket_ref.update(
        to_firestore(
            {
                "updated_at": now,
                "resolution": {
                    "text": text,
                    "sent_at": now,
                    "delivery_state": ProviderStatus.QUEUED,
                    "attempts": resolution.get("attempts", 0) + 1,
                },
            }
        )
    )

    ticket_ref.collection("events").document().set(
        to_firestore(
            {
                "type": EventType.RESOLUTION_SENT,
                "from": current,
                "to": current,
                "actor": "admin",
                "actor_uid": actor_uid,
                "note": f"Resent as {sent_via}",
                "at": now,
            }
        )
    )

    return message_id
