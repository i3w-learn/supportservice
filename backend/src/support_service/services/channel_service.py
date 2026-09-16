"""WhatsApp channel: normalize inbound Gupshup payloads, send outbound
messages, and orchestrate one inbound message end to end (§3, §4.1).

Note on module layout: this module and `ticket_service` depend on each other
(`create_ticket` is used by `handle_inbound` below; `send_text` / `send_template`
defined here are used by `ticket_service.resolve_ticket` / `resend_resolution`).
To let that circular import resolve, each module defines the names the
*other* module needs before importing from it — see the cross-import below
and the matching comment in `ticket_service.py`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from ulid import ULID

from support_service.config import defaults
from support_service.config.defaults import seed
from support_service.config.models import ConfigSnapshot
from support_service.conversation.routing import (
    ContinueSession,
    OfferReturningOptions,
    route,
)
from support_service.conversation.steps import (
    Draft,
    Reply,
    Row,
    SendList,
    SendTemplate,
    SendText,
    Turn,
    advance,
    begin,
    finish_idle,
    offer_returning,
)
from support_service.models import (
    Attachment,
    AttachmentState,
    Contact,
    InboundMessage,
    Language,
    MessageType,
    OpenTicket,
    Session,
    Step,
    TicketStatus,
)
from support_service.repositories.base import from_firestore, get_db, to_firestore
from support_service.services import task_service

# --- normalize: Gupshup payload -> InboundMessage --------------------------
#
# This is the one place that knows Gupshup's JSON shape. Everything
# downstream sees only the normalized InboundMessage from models.py.

_TYPE_MAP: dict[str, MessageType] = {
    "text": MessageType.TEXT,
    "image": MessageType.IMAGE,
    "video": MessageType.VIDEO,
    "file": MessageType.DOCUMENT,
    "audio": MessageType.DOCUMENT,
    "list_reply": MessageType.INTERACTIVE,
    "button_reply": MessageType.INTERACTIVE,
    "quick_reply": MessageType.INTERACTIVE,
}

_MEDIA_TYPES = {"image", "video", "file", "audio"}

_MIME_GUESS: dict[str, str] = {
    "image": "image/jpeg",
    "video": "video/mp4",
    "file": "application/octet-stream",
    "audio": "audio/ogg",
}


def normalize(raw: dict[str, Any]) -> InboundMessage:
    payload = raw["payload"]
    inner = payload.get("payload", {})
    gupshup_type = payload["type"]

    msg_type = _TYPE_MAP.get(gupshup_type, MessageType.TEXT)

    text: str | None = None
    reply_id: str | None = None
    attachment: Attachment | None = None
    context_message_id: str | None = None

    if gupshup_type == "text":
        text = inner.get("text")

    elif gupshup_type in ("list_reply", "quick_reply"):
        text = inner.get("title")
        reply_id = inner.get("postbackText") or inner.get("id")

    elif gupshup_type == "button_reply":
        text = inner.get("title")
        reply_id = inner.get("id")

    elif gupshup_type in _MEDIA_TYPES:
        text = inner.get("caption")
        attachment = Attachment(
            state=AttachmentState.PENDING,
            mime_type=inner.get("contentType") or _MIME_GUESS.get(gupshup_type),
            media_url=inner.get("url"),
        )

    context = payload.get("context")
    if context:
        context_message_id = context.get("id")

    ts = raw.get("timestamp", 0)
    received_at = datetime.fromtimestamp(ts / 1000, tz=UTC) if ts else datetime.now(UTC)

    return InboundMessage(
        provider_message_id=payload["id"],
        wa_number=payload["source"],
        type=msg_type,
        text=text,
        sender_name=payload.get("sender", {}).get("name"),
        reply_id=reply_id,
        context_message_id=context_message_id,
        attachment=attachment,
        received_at=received_at,
    )


# --- send: outbound messages to Gupshup ------------------------------------
#
# Every send returns the Gupshup messageId.

API_URL = "https://api.gupshup.io/wa/api/v1/msg"


@dataclass
class GupshupConfig:
    api_key: str
    app_name: str
    source_number: str


def _config() -> GupshupConfig:
    return GupshupConfig(
        api_key=os.environ["GUPSHUP_API_KEY"],
        app_name=os.environ["GUPSHUP_APP_NAME"],
        source_number=os.environ["GUPSHUP_SOURCE_NUMBER"],
    )


def _send(destination: str, message: dict[str, Any]) -> str:
    cfg = _config()
    response = httpx.post(
        API_URL,
        headers={"apikey": cfg.api_key},
        data={
            "channel": "whatsapp",
            "source": cfg.source_number,
            "destination": destination,
            "src.name": cfg.app_name,
            "message": json.dumps(message),
        },
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json().get("messageId", "")


def send_text(to: str, text: str) -> str:
    return _send(to, {"type": "text", "text": text})


def send_list(to: str, body: str, button_title: str, rows: list[Row]) -> str:
    return _send(
        to,
        {
            "type": "list",
            "title": body[:60],
            "body": body,
            "msgid": "list",
            "globalButtons": [{"type": "text", "title": button_title[:20]}],
            "items": [
                {
                    "title": "Options",
                    "options": [
                        {"type": "text", "title": row.label[:24], "postbackText": row.id}
                        for row in rows
                    ],
                }
            ],
        },
    )


def send_template(to: str, template_name: str, language: str, params: list[str]) -> str:
    return _send(
        to,
        {
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"policy": "deterministic", "code": language},
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": p} for p in params],
                    }
                ],
            },
        },
    )


def send_reply(to: str, reply: Reply) -> str:
    if isinstance(reply, SendText):
        return send_text(to, reply.body)
    if isinstance(reply, SendList):
        return send_list(to, reply.body, "Choose", list(reply.rows))
    if isinstance(reply, SendTemplate):
        return send_template(to, reply.name, reply.language.value, list(reply.params))
    raise ValueError(f"Unknown reply type: {type(reply)}")


def log_outbound(
    db: Any,
    wa_number: str,
    message_id: str,
    text: str | None,
    now: datetime,
    *,
    ticket_id: str | None = None,
    sent_via: str = "freeform",
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
                "sent_via": sent_via,
                "provider_status": "queued",
                "created_at": now,
            }
        )
    )
    db.collection("contacts").document(wa_number).update({"lastOutboundAt": now, "updatedAt": now})


# `ticket_service` needs `send_text` / `send_template` / `log_outbound` above;
# this module needs `ticket_service.create_ticket` / `schedule_sla_checks` below.
# See module docstring.
from support_service.services.ticket_service import (  # noqa: E402
    create_ticket,
)

# --- handle: inbound message orchestration ----------------------------------
#
# dedupe -> normalize -> route -> step -> reply -> persist.


def handle_inbound(raw: dict[str, Any]) -> None:
    now = datetime.now(UTC)
    message = normalize(raw)
    db = get_db()

    if _is_duplicate(db, message.provider_message_id):
        return

    config = seed()
    contact_data = _ensure_contact(db, message, now)
    contact = _drop_stale_session(
        db, Contact(**from_firestore(contact_data)), message.wa_number, config, now
    )

    _append_message(db, message, now)
    _update_last_inbound(db, message.wa_number, now)
    if message.attachment:
        task_service.enqueue(
            "/tasks/media",
            {"wa_number": message.wa_number, "message_id": message.provider_message_id},
        )

    decision = route(contact, _load_open_tickets(db, contact))
    language = contact.language or Language.EN

    if isinstance(decision, ContinueSession):
        turn = advance(contact, message, config, now=now)
    elif isinstance(decision, OfferReturningOptions):
        turn = offer_returning(decision.ticket, language, now=now)
    else:
        turn = begin(contact, config, now=now)

    _apply(db, message.wa_number, turn, config, now)


def _apply(db: Any, wa_number: str, turn: Turn, config: ConfigSnapshot, now: datetime) -> None:
    """Send what the step machine decided, then persist what it left behind."""
    _send_replies(wa_number, turn.replies, db, now)

    if turn.learned_language:
        db.collection("contacts").document(wa_number).update(
            {"language": turn.learned_language.value}
        )

    if turn.create:
        _complete_report(db, wa_number, turn.create, config, now)
    elif turn.session:
        _update_session(db, wa_number, turn.session, now)
        if turn.session.step is Step.MEDIA:
            _schedule_idle_check(wa_number, turn.session, config)
    else:
        # Nothing left to answer — the flow is over.
        db.collection("contacts").document(wa_number).update({"session": None, "updatedAt": now})


def finish_idle_session(wa_number: str) -> str | None:
    """File the report for a contact who never sent a photo or tapped Skip.

    Runs as a delayed Cloud Task. Every media-step message schedules one, so
    all but the last find the contact still active and do nothing.
    """
    now = datetime.now(UTC)
    db = get_db()
    ref = db.collection("contacts").document(wa_number)
    snap = ref.get()
    session_data = (snap.to_dict() or {}).get("session") if snap.exists else None
    if not session_data:
        return None

    session = Session(**from_firestore(session_data))
    config = seed()
    if now - session.last_activity_at < timedelta(seconds=config.settings.media_idle_seconds):
        return None

    draft = finish_idle(session)
    if draft is None:
        ref.update({"session": None, "updatedAt": now})
        return None

    return _complete_report(db, wa_number, draft, config, now)


def _complete_report(
    db: Any, wa_number: str, draft: Draft, config: ConfigSnapshot, now: datetime
) -> str:
    ticket_id = create_ticket(draft, wa_number, now=now)
    language = Language(draft.language)
    confirmation = SendTemplate(
        defaults.TICKET_CREATED,
        language,
        (ticket_id, config.category_label(draft.category_id, language), f"+{wa_number}"),
    )
    _send_replies(wa_number, (confirmation,), db, now, ticket_id=ticket_id)
    _stamp_ticket_on_messages(db, wa_number, ticket_id, now)
    return ticket_id


def _drop_stale_session(
    db: Any, contact: Contact, wa_number: str, config: ConfigSnapshot, now: datetime
) -> Contact:
    """Forget a flow abandoned long ago, so an old step can't swallow a fresh "Hi"."""
    session = contact.session
    expiry = timedelta(hours=config.settings.session_expiry_hours)
    if session is None or now - session.started_at < expiry:
        return contact
    db.collection("contacts").document(wa_number).update({"session": None, "updatedAt": now})
    return contact.model_copy(update={"session": None})


def _schedule_idle_check(wa_number: str, session: Session, config: ConfigSnapshot) -> None:
    # A few seconds past the idle window, so the check never lands just before it.
    delay = timedelta(seconds=config.settings.media_idle_seconds + 5)
    task_service.enqueue(
        "/tasks/idle", {"wa_number": wa_number}, at=session.last_activity_at + delay
    )


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
        data = doc.to_dict()
        # The WhatsApp profile name is the only name we get — the flow no
        # longer asks for one.
        if message.sender_name and not data.get("displayName"):
            ref.update({"displayName": message.sender_name})
            data["displayName"] = message.sender_name
        return data

    data = to_firestore(
        {
            "wa_number": message.wa_number,
            "display_name": message.sender_name,
            "language": None,
            "session": None,
            "open_ticket_ids": [],
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
    for ticket_id in contact.open_ticket_ids:
        doc = db.collection("tickets").document(ticket_id).get()
        if not doc.exists:
            continue
        data = doc.to_dict()
        tickets.append(
            OpenTicket(
                ticket_id=ticket_id,
                category_id=data.get("categoryId", ""),
                category_label=data.get("categoryLabel", ""),
                status=TicketStatus(data.get("status", TicketStatus.OPEN)),
                created_at=data.get("createdAt") or datetime.now(UTC),
            )
        )
    return tickets


def _send_replies(
    wa_number: str,
    replies: tuple[Reply, ...],
    db: Any,
    now: datetime,
    *,
    ticket_id: str | None = None,
) -> None:
    for reply in replies:
        message_id = send_reply(wa_number, reply)
        log_outbound(
            db,
            wa_number,
            message_id,
            _reply_text(reply),
            now,
            ticket_id=ticket_id,
            sent_via="template" if isinstance(reply, SendTemplate) else "freeform",
        )


def _reply_text(reply: Reply) -> str | None:
    """What to show in the dashboard. A template's wording lives in Gupshup,
    so record its name and the values we filled in."""
    if isinstance(reply, SendTemplate):
        return " · ".join((f"[{reply.name}]", *reply.params))
    return reply.body


def _update_session(db: Any, wa_number: str, session: Any, now: datetime) -> None:
    db.collection("contacts").document(wa_number).update(
        to_firestore({"session": session.model_dump(), "updated_at": now})
    )


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
