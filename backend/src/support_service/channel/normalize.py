"""Turn a Gupshup webhook payload into an InboundMessage.

This is the one file that knows Gupshup's JSON shape. Everything downstream
sees only the normalized InboundMessage from models.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from support_service.models import Attachment, AttachmentState, InboundMessage, MessageType

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
            mime_type=inner.get("mimeType") or _MIME_GUESS.get(gupshup_type),
            media_id=inner.get("mediaId"),
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
        reply_id=reply_id,
        context_message_id=context_message_id,
        attachment=attachment,
        received_at=received_at,
    )
