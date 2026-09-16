"""Ticket lifecycle: creation, status transitions, resolution (§4.3, §8).

Note on module layout: this module and `channel_service` depend on each other
(`create_ticket` is used by `channel_service.handle_inbound`; `send_template` /
`log_outbound` are used by `resolve_ticket` / `resend_resolution` below). To
let that circular import resolve, each module defines the names the *other*
module needs before importing from it. Don't reorder the sections below
without checking `channel_service.py`'s matching comment.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from google.cloud.firestore_v1 import transaction as fs_transaction

from support_service.config.defaults import TICKET_RESOLVED, seed
from support_service.conversation.steps import Draft
from support_service.models import EventType, Language, ProviderStatus, SlaState, TicketStatus
from support_service.repositories.base import get_db, get_doc, to_firestore
from support_service.services import task_service

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
    config = seed()
    language = Language(draft.language)

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

        ticket_data = to_firestore(
            {
                "wa_number": wa_number,
                # The WhatsApp profile name — the flow no longer asks for one.
                "contact_name": contact_data.get("displayName"),
                "category_id": draft.category_id,
                "category_label": config.category_label(draft.category_id, language),
                "language": language,
                "description": draft.description,
                "attachment_count": 0,
                "status": TicketStatus.OPEN,
                "sla_state": SlaState.OK,
                "resolution": None,
                "created_at": now,
                "updated_at": now,
                "sla_started_at": now,
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

    ticket_id = _txn(db.transaction())
    schedule_sla_checks(ticket_id, now)
    return ticket_id


def schedule_sla_checks(ticket_id: str, start: datetime) -> None:
    """One delayed check per deadline, counted from creation or reopen (§11)."""
    settings = seed().settings
    # A minute past each deadline, so clock skew never runs the check early.
    for hours in (settings.sla_reminder_hours, settings.sla_breach_hours):
        task_service.enqueue(
            "/tasks/sla", {"ticket_id": ticket_id}, at=start + timedelta(hours=hours, minutes=1)
        )


# `channel_service` needs `create_ticket` / `schedule_sla_checks` above; this
# module needs `channel_service.send_template` / `log_outbound` below.
# See module docstring.
from support_service.services.channel_service import log_outbound, send_template  # noqa: E402

# --- resolution — send and manage the resolved/closed lifecycle (§4.3) ----


def resolve_ticket(ticket_id: str, text: str, actor_uid: str) -> str:
    ticket = get_doc("tickets", ticket_id)
    if not ticket:
        raise ValueError(f"Ticket {ticket_id} not found")

    current = TicketStatus(ticket["status"])
    validate_transition(current, TicketStatus.RESOLVED)

    now = datetime.now(UTC)
    message_id = _send_resolution(ticket, ticket_id, text)

    db = get_db()
    # The delivery receipt closes the ticket by looking this record up by
    # message id (webhook_controller), so the send must be recorded.
    log_outbound(
        db,
        ticket["wa_number"],
        message_id,
        text,
        now,
        ticket_id=ticket_id,
        sent_via="template",
    )

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
                "note": "Sent as template",
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
    now = datetime.now(UTC)
    message_id = _send_resolution(ticket, ticket_id, text)

    db = get_db()
    log_outbound(
        db,
        ticket["wa_number"],
        message_id,
        text,
        now,
        ticket_id=ticket_id,
        sent_via="template",
    )

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
                "note": "Resent as template",
                "at": now,
            }
        )
    )

    return message_id


def _send_resolution(ticket: dict, ticket_id: str, text: str) -> str:
    """Always the approved template: the admin usually replies hours later,
    long after the 24-hour window free text needs (§4.3)."""
    language = ticket.get("language") or Language.EN.value
    return send_template(ticket["wa_number"], TICKET_RESOLVED, language, [ticket_id, text])


# --- SLA — one delayed check per deadline, scheduled at creation (§11) -----


def check_sla(ticket_id: str, *, now: datetime | None = None) -> SlaState | None:
    """Flag an unanswered ticket that is past its reminder or breach deadline."""
    now = now or datetime.now(UTC)
    settings = seed().settings
    ticket_ref = get_db().collection("tickets").document(ticket_id)
    snap = ticket_ref.get()
    data = snap.to_dict() if snap.exists else None
    if not data or data.get("status") not in (TicketStatus.OPEN, TicketStatus.IN_PROGRESS):
        return None

    # A reopened ticket's clock restarts at the reopen, not at creation.
    started = data.get("slaStartedAt") or data.get("createdAt")
    if not started:
        return None

    current = data.get("slaState", SlaState.OK)
    age = now - started
    if age >= timedelta(hours=settings.sla_breach_hours) and current != SlaState.BREACHED:
        new_state = SlaState.BREACHED
        note = f"{settings.sla_breach_hours}h with no resolution"
    elif age >= timedelta(hours=settings.sla_reminder_hours) and current == SlaState.OK:
        new_state = SlaState.REMINDER_DUE
        note = f"{settings.sla_reminder_hours}h with no first response"
    else:
        return None

    ticket_ref.update(to_firestore({"sla_state": new_state, "updated_at": now}))
    ticket_ref.collection("events").document().set(
        to_firestore(
            {
                "type": EventType.SLA_FLAGGED,
                "from": current,
                "to": new_state,
                "actor": "system",
                "actor_uid": None,
                "note": note,
                "at": now,
            }
        )
    )
    return new_state
