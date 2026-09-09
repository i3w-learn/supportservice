# backend/src/support_service/jobs/media_pass.py
"""2-minute cron: fetch pending media and finish idle description sessions (§7, §11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from support_service.channel.send import send_text
from support_service.config.defaults import seed
from support_service.conversation.steps import finish_idle
from support_service.firestore import from_firestore, get_db
from support_service.media import fetch_pending_media
from support_service.models import Language, Session
from support_service.tickets.create import create_ticket


def run_media_pass() -> dict[str, int]:
    media_count = fetch_pending_media()
    idle_count = _finish_idle_sessions()
    return {"media_fetched": media_count, "idle_finished": idle_count}


def _finish_idle_sessions() -> int:
    db = get_db()
    config = seed()
    idle_threshold = timedelta(seconds=config.settings.description_idle_seconds)
    cutoff = datetime.now(UTC) - idle_threshold

    idle = (
        db.collection("contacts")
        .where("session.step", "==", "description")
        .where("session.lastActivityAt", "<", cutoff)
        .limit(20)
        .get()
    )

    count = 0
    for doc in idle:
        data = from_firestore(doc.to_dict())
        session_data = data.get("session")
        if not session_data:
            continue

        session = Session(**session_data)
        draft = finish_idle(session)
        if draft is None:
            doc.reference.update({"session": None, "updatedAt": datetime.now(UTC)})
            continue

        try:
            ticket_id = create_ticket(draft, data["wa_number"])
            language = Language(draft.language) if draft.language else Language.EN
            confirmation = config.text("ticket_created", language).format(ticket_id=ticket_id)
            send_text(data["wa_number"], confirmation)
            count += 1
        except Exception:
            doc.reference.update({"session": None, "updatedAt": datetime.now(UTC)})

    return count
