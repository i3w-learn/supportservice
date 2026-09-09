"""Ticket creation — one Firestore transaction (§8)."""

from __future__ import annotations

from datetime import UTC, datetime

from google.cloud.firestore_v1 import transaction as fs_transaction

from support_service.conversation.steps import Draft
from support_service.firestore import get_db, to_firestore
from support_service.models import EventType, SlaState, TicketStatus


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
