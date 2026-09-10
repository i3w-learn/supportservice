"""Ticket-specific Firestore references and queries (§3, §8)."""

from __future__ import annotations

from typing import Any

from support_service.repositories.base import to_firestore

COLLECTION = "tickets"


def tickets(db: Any) -> Any:
    return db.collection(COLLECTION)


def ticket_ref(db: Any, ticket_id: str) -> Any:
    return tickets(db).document(ticket_id)


def ticket_events(db: Any, ticket_id: str) -> Any:
    return ticket_ref(db, ticket_id).collection("events")


def log_event(db: Any, ticket_id: str, event_data: dict[str, Any]) -> None:
    ticket_events(db, ticket_id).document().set(to_firestore(event_data))


def open_tickets_for_sla_sweep(db: Any, *, limit: int = 100) -> Any:
    return (
        tickets(db)
        .where("status", "in", ["open", "in_progress"])
        .where("slaState", "!=", "breached")
        .limit(limit)
    )
