"""Inbound message orchestration: dedupe → normalize → route → step → reply → persist."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ulid import ULID

from support_service.channel.normalize import normalize
from support_service.channel.send import send_reply, send_text
from support_service.config.defaults import seed
from support_service.conversation.routing import (
    AppendToTicket,
    AskAboutRecentlyClosed,
    ContinueSession,
    Disambiguate,
    ReopenTicket,
    StartReport,
    route,
)
from support_service.conversation.steps import Row, SendButtons, SendList, advance, begin
from support_service.firestore import from_firestore, get_db, to_firestore
from support_service.models import (
    Contact,
    EventType,
    InboundMessage,
    Language,
    OpenTicket,
    TicketStatus,
)
from support_service.tickets.create import create_ticket


def handle_inbound(raw: dict[str, Any]) -> None:
    now = datetime.now(UTC)
    message = normalize(raw)
    db = get_db()

    if _is_duplicate(db, message.provider_message_id):
        return

    contact_data = _ensure_contact(db, message, now)
    contact = Contact(**from_firestore(contact_data))

    _append_message(db, message, now)
    _update_last_inbound(db, message.wa_number, now)

    open_tickets = _load_open_tickets(db, contact)
    outbound_map = _load_outbound_map(db, message.wa_number)
    closed_ids = frozenset(ref.ticket_id for ref in contact.recently_closed) - frozenset(
        t.ticket_id for t in open_tickets
    )

    decision = route(
        contact,
        message,
        open_tickets,
        now=now,
        ticket_id_for_outbound=outbound_map,
        closed_ticket_ids=closed_ids,
    )

    config = seed()
    language = contact.language or Language.EN

    if isinstance(decision, StartReport):
        turn = begin(contact, config, now=now)
        _send_replies(message.wa_number, turn.replies, db, now)
        if turn.session:
            _update_session(db, message.wa_number, turn.session, now)
        if turn.learned_language:
            db.collection("contacts").document(message.wa_number).update(
                {"language": turn.learned_language.value}
            )

    elif isinstance(decision, ContinueSession):
        turn = advance(contact, message, config, now=now)
        _send_replies(message.wa_number, turn.replies, db, now)

        if turn.learned_language:
            db.collection("contacts").document(message.wa_number).update(
                {"language": turn.learned_language.value}
            )

        if turn.create:
            ticket_id = create_ticket(turn.create, message.wa_number, now=now)
            confirmation = config.text("ticket_created", Language(turn.create.language))
            confirmation = confirmation.format(ticket_id=ticket_id)
            _send_and_log(db, message.wa_number, confirmation, ticket_id, now)
            _stamp_ticket_on_messages(db, message.wa_number, ticket_id, now)
        elif turn.session:
            _update_session(db, message.wa_number, turn.session, now)

    elif isinstance(decision, AppendToTicket):
        _stamp_message(db, message, decision.ticket_id)
        _log_event(db, decision.ticket_id, EventType.MESSAGE_ADDED, now)
        db.collection("tickets").document(decision.ticket_id).update({"lastInboundAt": now})
        text = config.text("appended", language).format(ticket_id=decision.ticket_id)
        _send_and_log(db, message.wa_number, text, decision.ticket_id, now)

    elif isinstance(decision, Disambiguate):
        rows = [Row(t.service_id, t.service_name) for t in decision.options] + [
            Row("new", config.text("new_problem", language))
        ]
        reply = SendList(config.text("ask_which_ticket", language), tuple(rows))
        _send_replies(message.wa_number, (reply,), db, now)

    elif isinstance(decision, AskAboutRecentlyClosed):
        service_name = decision.closed.service_id
        text = config.text("ask_recently_closed", language).format(
            service_name=service_name, ticket_id=decision.closed.ticket_id
        )
        buttons = (
            Row("reopen", config.text("yes_same", language)),
            Row("new", config.text("new_problem", language)),
        )
        reply = SendButtons(text, buttons)
        _send_replies(message.wa_number, (reply,), db, now)

    elif isinstance(decision, ReopenTicket):
        _reopen(db, decision.ticket_id, message.wa_number, now)
        text = config.text("reopened", language).format(ticket_id=decision.ticket_id)
        _send_and_log(db, message.wa_number, text, decision.ticket_id, now)


def _is_duplicate(db: Any, provider_message_id: str) -> bool:
    ref = db.collection("inbound").document(provider_message_id)
    if ref.get().exists:
        return True
    ref.set(
        {
            "receivedAt": datetime.now(UTC),
            "expiresAt": datetime.now(UTC) + timedelta(days=7),
        }
    )
    return False


def _ensure_contact(db: Any, message: InboundMessage, now: datetime) -> dict:
    ref = db.collection("contacts").document(message.wa_number)
    doc = ref.get()
    if doc.exists:
        return doc.to_dict()
    data = to_firestore(
        {
            "wa_number": message.wa_number,
            "display_name": None,
            "centre_name": None,
            "language": None,
            "session": None,
            "open_ticket_ids": [],
            "recently_closed": [],
            "last_inbound_at": now,
            "last_outbound_at": None,
            "created_at": now,
            "updated_at": now,
        }
    )
    ref.set(data)
    return data


def _append_message(db: Any, message: InboundMessage, now: datetime) -> None:
    data = to_firestore(
        {
            "message_id": message.provider_message_id,
            "direction": "in",
            "ticket_id": None,
            "type": message.type,
            "text": message.text,
            "created_at": now,
        }
    )
    if message.attachment:
        data["attachment"] = to_firestore(message.attachment.model_dump())
    db.collection("contacts").document(message.wa_number).collection("messages").document(
        message.provider_message_id
    ).set(data)


def _update_last_inbound(db: Any, wa_number: str, now: datetime) -> None:
    db.collection("contacts").document(wa_number).update({"lastInboundAt": now, "updatedAt": now})


def _load_open_tickets(db: Any, contact: Contact) -> list[OpenTicket]:
    tickets = []
    for tid in contact.open_ticket_ids:
        doc = db.collection("tickets").document(tid).get()
        if doc.exists:
            data = doc.to_dict()
            tickets.append(
                OpenTicket(
                    ticket_id=tid,
                    service_id=data.get("serviceId", ""),
                    service_name=data.get("serviceName", ""),
                )
            )
    return tickets


def _load_outbound_map(db: Any, wa_number: str) -> dict[str, str]:
    outbound = (
        db.collection("contacts")
        .document(wa_number)
        .collection("messages")
        .where("direction", "==", "out")
        .where("ticketId", "!=", None)
        .order_by("createdAt", direction="DESCENDING")
        .limit(20)
        .get()
    )
    return {
        doc.to_dict().get("messageId", ""): doc.to_dict().get("ticketId", "")
        for doc in outbound
        if doc.to_dict().get("messageId")
    }


def _send_replies(wa_number: str, replies: tuple, db: Any, now: datetime) -> None:
    for reply in replies:
        message_id = send_reply(wa_number, reply)
        text = reply.body if hasattr(reply, "body") else None
        _log_outbound(db, wa_number, message_id, text, now)


def _send_and_log(db: Any, wa_number: str, text: str, ticket_id: str, now: datetime) -> None:
    message_id = send_text(wa_number, text)
    _log_outbound(db, wa_number, message_id, text, now, ticket_id=ticket_id)


def _log_outbound(
    db: Any,
    wa_number: str,
    message_id: str,
    text: str | None,
    now: datetime,
    *,
    ticket_id: str | None = None,
) -> None:
    ulid = str(ULID())
    db.collection("contacts").document(wa_number).collection("messages").document(ulid).set(
        to_firestore(
            {
                "message_id": message_id or ulid,
                "direction": "out",
                "ticket_id": ticket_id,
                "type": "text",
                "text": text,
                "sent_via": "freeform",
                "provider_status": "queued",
                "created_at": now,
            }
        )
    )
    db.collection("contacts").document(wa_number).update({"lastOutboundAt": now, "updatedAt": now})


def _update_session(db: Any, wa_number: str, session: Any, now: datetime) -> None:
    db.collection("contacts").document(wa_number).update(
        to_firestore({"session": session.model_dump(), "updated_at": now})
    )


def _stamp_message(db: Any, message: InboundMessage, ticket_id: str) -> None:
    db.collection("contacts").document(message.wa_number).collection("messages").document(
        message.provider_message_id
    ).update({"ticketId": ticket_id})


def _stamp_ticket_on_messages(db: Any, wa_number: str, ticket_id: str, now: datetime) -> None:
    unstamped = (
        db.collection("contacts")
        .document(wa_number)
        .collection("messages")
        .where("ticketId", "==", None)
        .get()
    )
    for doc in unstamped:
        doc.reference.update({"ticketId": ticket_id})


def _log_event(db: Any, ticket_id: str, event_type: EventType, now: datetime) -> None:
    db.collection("tickets").document(ticket_id).collection("events").document().set(
        to_firestore(
            {
                "type": event_type,
                "from": None,
                "to": None,
                "actor": "bot",
                "actor_uid": None,
                "note": None,
                "at": now,
            }
        )
    )


def _reopen(db: Any, ticket_id: str, wa_number: str, now: datetime) -> None:
    from google.cloud.firestore_v1 import transaction as fs_transaction

    @fs_transaction.transactional
    def _txn(txn: fs_transaction.Transaction) -> None:
        ticket_ref = db.collection("tickets").document(ticket_id)
        contact_ref = db.collection("contacts").document(wa_number)

        ticket_snap = ticket_ref.get(transaction=txn)
        contact_snap = contact_ref.get(transaction=txn)

        ticket_data = ticket_snap.to_dict() or {}
        contact_data = contact_snap.to_dict() or {}

        open_ids: list[str] = contact_data.get("openTicketIds", [])
        service_id = ticket_data.get("serviceId")
        for oid in open_ids:
            other = db.collection("tickets").document(oid).get(transaction=txn)
            if other.exists and other.to_dict().get("serviceId") == service_id:
                return

        txn.update(
            ticket_ref,
            to_firestore(
                {
                    "status": TicketStatus.OPEN,
                    "sla_state": "ok",
                    "closed_at": None,
                    "updated_at": now,
                }
            ),
        )

        recently_closed = [
            rc for rc in contact_data.get("recentlyClosed", []) if rc.get("ticketId") != ticket_id
        ]
        txn.update(
            contact_ref,
            {
                "openTicketIds": open_ids + [ticket_id],
                "recentlyClosed": recently_closed,
                "updatedAt": now,
            },
        )

        event_ref = ticket_ref.collection("events").document()
        txn.set(
            event_ref,
            to_firestore(
                {
                    "type": EventType.STATUS_CHANGED,
                    "from": TicketStatus.CLOSED,
                    "to": TicketStatus.OPEN,
                    "actor": "bot",
                    "actor_uid": None,
                    "note": "Reopened by contact",
                    "at": now,
                }
            ),
        )

    _txn(db.transaction())
