"""Webhook endpoints — Gupshup delivers inbound messages and receipts here."""

from __future__ import annotations

import hmac
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query, Response

from support_service.models import EventType, ProviderStatus, TicketStatus
from support_service.repositories.base import get_db, to_firestore
from support_service.repositories.contact_repository import contact_ref as _contact_ref
from support_service.repositories.message_repository import find_by_message_id
from support_service.repositories.ticket_repository import log_event as _log_ticket_event
from support_service.repositories.ticket_repository import ticket_ref as _ticket_ref
from support_service.services.channel_service import handle_inbound

router = APIRouter(prefix="/webhook", tags=["webhook"])


def _check_secret(secret: str | None) -> bool:
    expected = os.environ.get("WEBHOOK_SECRET", "")
    if not expected:
        return False  # fail-closed: no secret configured = reject
    if not secret:
        return False
    return hmac.compare_digest(secret, expected)


@router.post("/gupshup")
def inbound(body: dict[str, Any], secret: str | None = Query(None)) -> Response:
    if not _check_secret(secret):
        return Response(status_code=401)

    msg_type = body.get("type")
    if msg_type != "message":
        return Response(status_code=200)

    handle_inbound(body)
    return Response(status_code=200)


@router.post("/gupshup/status")
def receipt(body: dict[str, Any], secret: str | None = Query(None)) -> Response:
    if not _check_secret(secret):
        return Response(status_code=401)

    if body.get("type") != "message-event":
        return Response(status_code=200)

    payload = body.get("payload", {})
    event_type = payload.get("type")
    gs_id = payload.get("gsId", "")

    status_map = {
        "enqueued": ProviderStatus.QUEUED,
        "sent": ProviderStatus.SENT,
        "delivered": ProviderStatus.DELIVERED,
        "read": ProviderStatus.READ,
        "failed": ProviderStatus.FAILED,
    }

    provider_status = status_map.get(event_type)
    if not provider_status or not gs_id:
        return Response(status_code=200)

    _update_message_status(gs_id, provider_status)

    if provider_status == ProviderStatus.DELIVERED:
        _try_close_on_delivery(gs_id)
    elif provider_status == ProviderStatus.FAILED:
        _mark_resolution_failed(gs_id)

    return Response(status_code=200)


def _update_message_status(gs_id: str, status: ProviderStatus) -> None:
    db = get_db()
    doc = find_by_message_id(db, gs_id)
    if doc is not None:
        doc.reference.update({"providerStatus": status.value})


def _try_close_on_delivery(gs_id: str) -> None:
    db = get_db()
    now = datetime.now(UTC)

    doc = find_by_message_id(db, gs_id)
    if doc is None:
        return

    msg_data = doc.to_dict()
    ticket_id = msg_data.get("ticketId")
    if not ticket_id:
        return

    ticket_ref = _ticket_ref(db, ticket_id)
    ticket_snap = ticket_ref.get()
    if not ticket_snap.exists:
        return

    ticket_data = ticket_snap.to_dict()
    if ticket_data.get("status") != TicketStatus.RESOLVED:
        return

    wa_number = ticket_data.get("waNumber")

    ticket_ref.update(
        to_firestore(
            {
                "status": TicketStatus.CLOSED,
                "closed_at": now,
                "updated_at": now,
                "resolution.delivery_state": ProviderStatus.DELIVERED,
            }
        )
    )

    _log_ticket_event(
        db,
        ticket_id,
        {
            "type": EventType.DELIVERED,
            "from": TicketStatus.RESOLVED,
            "to": TicketStatus.CLOSED,
            "actor": "system",
            "actor_uid": None,
            "note": "Delivery receipt received",
            "at": now,
        },
    )

    if wa_number:
        contact_ref = _contact_ref(db, wa_number)
        contact_snap = contact_ref.get()
        if contact_snap.exists:
            contact_data = contact_snap.to_dict()
            open_ids = [oid for oid in contact_data.get("openTicketIds", []) if oid != ticket_id]
            recently_closed = contact_data.get("recentlyClosed", [])
            recently_closed.append(
                {
                    "ticketId": ticket_id,
                    "serviceId": ticket_data.get("serviceId"),
                    "closedAt": now,
                }
            )
            contact_ref.update(
                {
                    "openTicketIds": open_ids,
                    "recentlyClosed": recently_closed,
                    "updatedAt": now,
                }
            )


def _mark_resolution_failed(gs_id: str) -> None:
    db = get_db()
    now = datetime.now(UTC)

    doc = find_by_message_id(db, gs_id)
    if doc is None:
        return

    msg_data = doc.to_dict()
    ticket_id = msg_data.get("ticketId")
    if not ticket_id:
        return

    ticket_ref = _ticket_ref(db, ticket_id)
    ticket_snap = ticket_ref.get()
    if not ticket_snap.exists:
        return

    ticket_data = ticket_snap.to_dict()
    if ticket_data.get("status") != TicketStatus.RESOLVED:
        return

    ticket_ref.update(
        to_firestore(
            {
                "updated_at": now,
                "resolution.delivery_state": ProviderStatus.FAILED,
            }
        )
    )

    _log_ticket_event(
        db,
        ticket_id,
        {
            "type": EventType.NOTE,
            "from": None,
            "to": None,
            "actor": "system",
            "actor_uid": None,
            "note": "Delivery of resolution failed",
            "at": now,
        },
    )
