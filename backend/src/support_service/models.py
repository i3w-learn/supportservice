"""Normalized domain shapes — the contract at the channel boundary.

`conversation` and `tickets` work only with these. Nothing in this file knows
that Gupshup exists, which is what makes a BSP swap one module's problem (§3).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Language(StrEnum):
    EN = "en"
    HI = "hi"
    TE = "te"
    TA = "ta"


class TicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class SlaState(StrEnum):
    OK = "ok"
    REMINDER_DUE = "reminder_due"
    BREACHED = "breached"


class AttachmentState(StrEnum):
    PENDING = "pending"
    STORED = "stored"
    FAILED = "failed"


class MessageType(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
    INTERACTIVE = "interactive"


class SentVia(StrEnum):
    FREEFORM = "freeform"
    TEMPLATE = "template"


class ProviderStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class Flow(StrEnum):
    REPORT = "report"
    DISAMBIGUATE = "disambiguate"


class Step(StrEnum):
    """Keys into the step table (§7)."""

    LANGUAGE = "language"
    SERVICE = "service"
    NAME = "name"
    CENTRE = "centre"
    CATEGORY = "category"
    DESCRIPTION = "description"


class EventType(StrEnum):
    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    NOTE = "note"
    RESOLUTION_SENT = "resolution_sent"
    DELIVERED = "delivered"
    SLA_FLAGGED = "sla_flagged"
    MEDIA_FAILED = "media_failed"
    MESSAGE_ADDED = "message_added"


class Attachment(BaseModel):
    state: AttachmentState = AttachmentState.PENDING
    storage_path: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    attempts: int = 0
    media_id: str | None = None


class InboundMessage(BaseModel):
    """One message from a contact, already stripped of provider specifics."""

    provider_message_id: str
    wa_number: str
    type: MessageType
    text: str | None = None
    """For interactive replies: the id of the row or button the contact tapped."""
    reply_id: str | None = None
    """Set when the contact used WhatsApp's reply-swipe on one of our messages."""
    context_message_id: str | None = None
    attachment: Attachment | None = None
    received_at: datetime

    @property
    def has_media(self) -> bool:
        return self.attachment is not None


class Session(BaseModel):
    """In-flight bot flow. Null on the contact means idle (§5)."""

    flow: Flow
    step: Step
    draft: dict[str, str] = Field(default_factory=dict)
    started_at: datetime
    last_activity_at: datetime


class ClosedTicketRef(BaseModel):
    """An entry in `recentlyClosed`. Without these, `closed -> open` is unreachable."""

    ticket_id: str
    service_id: str
    closed_at: datetime


class Contact(BaseModel):
    """Root record, one per phone number (§5)."""

    wa_number: str
    display_name: str | None = None
    centre_name: str | None = None
    language: Language | None = None
    session: Session | None = None
    open_ticket_ids: list[str] = Field(default_factory=list)
    recently_closed: list[ClosedTicketRef] = Field(default_factory=list)
    last_inbound_at: datetime | None = None
    last_outbound_at: datetime | None = None


class OpenTicket(BaseModel):
    """The slice of a ticket that routing needs. Not the whole document."""

    ticket_id: str
    service_id: str
    service_name: str
