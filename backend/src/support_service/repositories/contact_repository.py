"""Contact-specific Firestore references and queries (§3, §5)."""

from __future__ import annotations

from typing import Any

COLLECTION = "contacts"


def contacts(db: Any) -> Any:
    return db.collection(COLLECTION)


def contact_ref(db: Any, wa_number: str) -> Any:
    return contacts(db).document(wa_number)


def contact_messages(db: Any, wa_number: str) -> Any:
    return contact_ref(db, wa_number).collection("messages")


def outbound_messages_with_ticket(db: Any, wa_number: str, *, limit: int = 20) -> Any:
    return (
        contact_messages(db, wa_number)
        .where("direction", "==", "out")
        .where("ticketId", "!=", None)
        .order_by("createdAt", direction="DESCENDING")
        .limit(limit)
    )


def expired_sessions(db: Any, cutoff: Any, *, limit: int = 50) -> Any:
    return contacts(db).where("session.startedAt", "<", cutoff).limit(limit)


def idle_description_sessions(db: Any, cutoff: Any, *, limit: int = 20) -> Any:
    return (
        contacts(db)
        .where("session.step", "==", "description")
        .where("session.lastActivityAt", "<", cutoff)
        .limit(limit)
    )


def contacts_with_recently_closed(db: Any, *, limit: int = 50) -> Any:
    return contacts(db).where("recentlyClosed", "!=", []).limit(limit)
