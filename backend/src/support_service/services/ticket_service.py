"""Ticket lifecycle: creation, status transitions, resolution (§4.3, §8).

Note on module layout: this module and `channel_service` depend on each other
(`create_ticket` is used by `channel_service.handle_inbound`; `send_text` /
`send_template` are used by `resolve_ticket` / `resend_resolution` below). To
let that circular import resolve, each module defines the names the *other*
module needs before importing from it. Don't reorder the sections below
without checking `channel_service.py`'s matching comment.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from google.cloud.firestore_v1 import transaction as fs_transaction

from support_service.conversation.steps import Draft
from support_service.models import EventType, ProviderStatus, SlaState, TicketStatus
from support_service.repositories.base import get_db, get_doc, to_firestore

# --- status transitions (§8) ----------------------------------------------

LEGAL: dict[TicketStatus, list[TicketStatus]] = {
    TicketStatus.OPEN: [TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED],
    TicketStatus.IN_PROGRESS: [TicketStatus.OPEN, TicketStatus.RESOLVED],
    TicketStatus.RESOLVED: [TicketStatus.CLOSED, TicketStatus.IN_PROGRESS],
    TicketStatus.CLOSED: [TicketStatus.OPEN],
}


def validate_transition(from_status: TicketStatus, to_status: TicketStatus) -> None:
    """Anything not listed in LEGAL is a 409."""
    if to_status not in LEGAL.get(from_status, []):
        raise ValueError(f"{from_status} → {to_status} is not a legal transition")


# --- creation — one Firestore transaction (§8) -----------------------------


def _ticket_id(date: datetime, seq: int) -> str:
    return f"TKT-{date.strftime('%Y%m%d')}-{seq:04d}"


def create_ticket(draft: Draft, wa_number: str, *, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    db = get_db()

    @fs_transaction.transactional
    def _txn(txn: fs_transaction.Transaction) -> str:
        counter_ref = db.collection("counters").document(now.strftime("%Y%m%d"))
        counter_snap = counter_ref.get(transaction=txn)
        seq = (counter_snap.to_dict() or {}).get("seq", 0) + 1

        ticket_id = _ticket_id(now, seq)
        ticket_ref = db.collection("tickets").document(ticket_id)
        contact_ref = db.collection("contacts").document(wa_number)

        contact_snap = contact_ref.get(transaction=txn)
        contact_data = contact_snap.to_dict() or {}
        open_ids: list[str] = contact_data.get("openTicketIds", [])

        for existing_id in open_ids:
            existing = db.collection("tickets").document(existing_id).get(transaction=txn)
            if existing.exists and existing.to_dict().get("serviceId") == draft.service_id:
                raise ValueError(f"Already open for this product: {existing_id}")

        config_service = db.collection("services").document(draft.service_id).get()
        service_data = config_service.to_dict() or {}
        service_name = service_data.get("name", {}).get(draft.language, draft.service_id)
        category_label = draft.category_id
        for cat in service_data.get("categories", []):
            if cat.get("id") == draft.category_id:
                category_label = cat.get("label", {}).get(draft.language, draft.category_id)
                break

        ticket_data = to_firestore(
            {
                "wa_number": wa_number,
                "contact_name": draft.display_name,
                "centre_name": draft.centre_name,
                "service_id": draft.service_id,
                "service_name": service_name,
                "category_id": draft.category_id,
                "category_label": category_label,
                "language": draft.language,
                "description": draft.description,
                "attachment_count": 0,
                "status": TicketStatus.OPEN,
                "sla_state": SlaState.OK,
                "resolution": None,
                "created_at": now,
                "updated_at": now,
                "first_response_at": None,
                "resolved_at": None,
                "closed_at": None,
                "last_inbound_at": now,
            }
        )

        event_data = to_firestore(
            {
                "type": EventType.CREATED,
                "from": None,
                "to": None,
                "actor": "bot",
                "actor_uid": None,
                "note": None,
                "at": now,
            }
        )

        txn.set(counter_ref, {"seq": seq})
        txn.set(ticket_ref, ticket_data)
        txn.set(ticket_ref.collection("events").document(), event_data)
        txn.update(
            contact_ref,
            {
                "openTicketIds": open_ids + [ticket_id],
                "session": None,
                "updatedAt": now,
            },
        )

        return ticket_id

    return _txn(db.transaction())


# `channel_service` needs `create_ticket` above; this module needs
# `channel_service.send_text` / `send_template` below. See module docstring.
from support_service.services.channel_service import send_template, send_text  # noqa: E402

TEMPLATE_NAMES: dict[str, str] = {
    "en": "i3w_b2g_support_bot_en",
    "hi": "i3w_b2g_support_bot_hi",
}
DEFAULT_TEMPLATE = "i3w_b2g_support_bot_en"


# --- resolution — send and manage the resolved/closed lifecycle (§4.3) ----


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
        template = TEMPLATE_NAMES.get(language, DEFAULT_TEMPLATE)
        message_id = send_template(wa_number, template, language, params)
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
        template = TEMPLATE_NAMES.get(language, DEFAULT_TEMPLATE)
        message_id = send_template(wa_number, template, language, params)
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
