"""Anganwadi centres: the master list the QR codes point at."""

from __future__ import annotations

from typing import Any

from support_service.models import CentreRef
from support_service.repositories.base import from_firestore

COLLECTION = "centres"


def centres(db: Any) -> Any:
    return db.collection(COLLECTION)


def centre_ref(db: Any, centre_id: str) -> Any:
    return centres(db).document(centre_id)


def find_centre(db: Any, centre_id: str) -> CentreRef | None:
    snap = centre_ref(db, centre_id).get()
    if not snap.exists:
        return None
    return _to_ref(centre_id, snap.to_dict() or {})


def find_centre_by_worker_phone(db: Any, wa_number: str) -> CentreRef | None:
    """Fallback when the greeting carried no id: the worker's own number."""
    for snap in centres(db).where("workerPhone", "==", wa_number).limit(1).get():
        return _to_ref(snap.id, snap.to_dict() or {})
    return None


def _to_ref(centre_id: str, data: dict[str, Any]) -> CentreRef:
    plain = from_firestore(data)
    return CentreRef(
        centre_id=centre_id,
        block=plain.get("block", ""),
        block_en=plain.get("block_en", ""),
        village=plain.get("village", ""),
        village_en=plain.get("village_en", ""),
    )
