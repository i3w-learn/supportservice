"""Message queries over the `messages` collection group (§3, §4.1, §9)."""

from __future__ import annotations

from typing import Any

COLLECTION_GROUP = "messages"


def messages_group(db: Any) -> Any:
    return db.collection_group(COLLECTION_GROUP)


def find_by_message_id(db: Any, message_id: str) -> Any | None:
    results = messages_group(db).where("messageId", "==", message_id).limit(1).get()
    return results[0] if results else None


def pending_attachments(db: Any, *, limit: int = 20) -> Any:
    return (
        messages_group(db)
        .where("attachment.state", "==", "pending")
        .order_by("createdAt")
        .limit(limit)
    )
