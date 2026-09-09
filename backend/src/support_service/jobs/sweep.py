# backend/src/support_service/jobs/sweep.py
"""Hourly sweep: SLA flagging, resolution retries, abandoned sessions, pruning (§11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from support_service.config.defaults import seed
from support_service.firestore import get_db, to_firestore
from support_service.models import EventType, SlaState


def run_sweep() -> dict[str, int]:
    sla_count = _flag_sla()
    expired_count = _clear_expired_sessions()
    pruned_count = _prune_recently_closed()
    return {
        "sla_flagged": sla_count,
        "sessions_expired": expired_count,
        "recently_closed_pruned": pruned_count,
    }


def _flag_sla() -> int:
    db = get_db()
    config = seed()
    now = datetime.now(UTC)
    reminder_cutoff = now - timedelta(hours=config.settings.sla_reminder_hours)
    breach_cutoff = now - timedelta(hours=config.settings.sla_breach_hours)
    count = 0

    open_tickets = (
        db.collection("tickets")
        .where("status", "in", ["open", "in_progress"])
        .where("slaState", "!=", "breached")
        .limit(100)
        .get()
    )

    for doc in open_tickets:
        data = doc.to_dict()
        created = data.get("createdAt")
        if not created:
            continue

        current_sla = data.get("slaState", "ok")

        if created <= breach_cutoff and current_sla != "breached":
            new_state = SlaState.BREACHED
            note = f"{config.settings.sla_breach_hours}h with no resolution"
        elif created <= reminder_cutoff and current_sla == "ok":
            new_state = SlaState.REMINDER_DUE
            note = f"{config.settings.sla_reminder_hours}h with no first response"
        else:
            continue

        doc.reference.update(to_firestore({"sla_state": new_state, "updated_at": now}))
        doc.reference.collection("events").document().set(
            to_firestore(
                {
                    "type": EventType.SLA_FLAGGED,
                    "from": current_sla,
                    "to": new_state,
                    "actor": "system",
                    "actor_uid": None,
                    "note": note,
                    "at": now,
                }
            )
        )
        count += 1

    return count


def _clear_expired_sessions() -> int:
    db = get_db()
    config = seed()
    cutoff = datetime.now(UTC) - timedelta(hours=config.settings.session_expiry_hours)
    count = 0

    expired = db.collection("contacts").where("session.startedAt", "<", cutoff).limit(50).get()

    for doc in expired:
        if doc.to_dict().get("session") is not None:
            doc.reference.update({"session": None, "updatedAt": datetime.now(UTC)})
            count += 1

    return count


def _prune_recently_closed() -> int:
    db = get_db()
    cutoff = datetime.now(UTC) - timedelta(days=7)
    count = 0

    contacts = db.collection("contacts").where("recentlyClosed", "!=", []).limit(50).get()

    for doc in contacts:
        data = doc.to_dict()
        original = data.get("recentlyClosed", [])
        pruned = [entry for entry in original if entry.get("closedAt", cutoff) > cutoff]
        if len(pruned) < len(original):
            doc.reference.update({"recentlyClosed": pruned, "updatedAt": datetime.now(UTC)})
            count += 1

    return count
