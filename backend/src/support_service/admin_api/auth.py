"""Firebase ID token verification and admin allowlist check (§9)."""

from __future__ import annotations

from time import time

from fastapi import HTTPException, Request
from firebase_admin import auth

from support_service.firestore import get_db

_CACHE_TTL = 60
_admin_cache: dict[str, float] = {}


def _is_admin(uid: str) -> bool:
    now = time()
    if uid in _admin_cache and now - _admin_cache[uid] < _CACHE_TTL:
        return True
    doc = get_db().collection("admins").document(uid).get()
    if doc.exists:
        _admin_cache[uid] = now
        return True
    return False


def get_admin_uid(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(401, "Missing or malformed Authorization header")

    token = header[7:]
    try:
        decoded = auth.verify_id_token(token)
    except Exception as exc:
        raise HTTPException(401, "Invalid token") from exc

    uid = decoded["uid"]
    if not _is_admin(uid):
        raise HTTPException(403, "Not an admin")

    return uid
