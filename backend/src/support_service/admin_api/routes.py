"""Admin REST endpoints (§9)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from support_service.admin_api.auth import get_admin_uid
from support_service.firestore import get_db, get_doc, to_firestore, update_doc
from support_service.models import EventType, TicketStatus
from support_service.tickets.resolution import resend_resolution as resend_ticket_resolution
from support_service.tickets.resolution import resolve_ticket
from support_service.tickets.transitions import validate_transition

router = APIRouter(prefix="/tickets", tags=["admin"], dependencies=[Depends(get_admin_uid)])


class StatusBody(BaseModel):
    to: TicketStatus
    note: str | None = None


class ResolutionBody(BaseModel):
    text: str


class NoteBody(BaseModel):
    text: str


@router.patch("/{ticket_id}/status")
def change_status(
    ticket_id: str, body: StatusBody, uid: str = Depends(get_admin_uid)
) -> dict[str, str]:
    ticket = get_doc("tickets", ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    current = TicketStatus(ticket["status"])
    try:
        validate_transition(current, body.to)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

    now = datetime.now(UTC)
    updates: dict = {
        "status": body.to,
        "updated_at": now,
    }
    if body.to == TicketStatus.IN_PROGRESS and ticket.get("first_response_at") is None:
        updates["first_response_at"] = now

    update_doc("tickets", ticket_id, updates)

    db = get_db()
    db.collection("tickets").document(ticket_id).collection("events").document().set(
        to_firestore(
            {
                "type": EventType.STATUS_CHANGED,
                "from": current,
                "to": body.to,
                "actor": "admin",
                "actor_uid": uid,
                "note": body.note,
                "at": now,
            }
        )
    )
    return {"status": "ok"}


@router.post("/{ticket_id}/resolution")
def send_resolution(
    ticket_id: str, body: ResolutionBody, uid: str = Depends(get_admin_uid)
) -> dict[str, str]:
    try:
        message_id = resolve_ticket(ticket_id, body.text, uid)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, "Send failed") from exc
    return {"status": "ok", "messageId": message_id}


@router.post("/{ticket_id}/notes")
def add_note(ticket_id: str, body: NoteBody, uid: str = Depends(get_admin_uid)) -> dict[str, str]:
    ticket = get_doc("tickets", ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    now = datetime.now(UTC)
    db = get_db()
    db.collection("tickets").document(ticket_id).collection("events").document().set(
        to_firestore(
            {
                "type": EventType.NOTE,
                "from": None,
                "to": None,
                "actor": "admin",
                "actor_uid": uid,
                "note": body.text,
                "at": now,
            }
        )
    )
    update_doc("tickets", ticket_id, {"updated_at": now})
    return {"status": "ok"}


@router.post("/{ticket_id}/resend")
def resend_resolution(ticket_id: str, uid: str = Depends(get_admin_uid)) -> dict[str, str]:
    ticket = get_doc("tickets", ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    resolution = ticket.get("resolution")
    if not resolution or ticket["status"] != TicketStatus.RESOLVED:
        raise HTTPException(409, "Nothing to resend")

    if resolution.get("delivery_state") != "failed":
        raise HTTPException(409, "Delivery did not fail")

    try:
        message_id = resend_ticket_resolution(ticket_id, uid)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, "Send failed") from exc
    return {"status": "ok", "messageId": message_id}
