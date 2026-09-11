"""Admin login — custom-token flow (no Firebase Auth provider needed)."""

from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, HTTPException
from firebase_admin import auth as fb_auth
from pydantic import BaseModel

from support_service.repositories.base import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

_SALT = b"support-service-admin-v1"


def hash_password(password: str) -> str:
    return hmac.new(_SALT, password.encode(), hashlib.sha256).hexdigest()


class LoginBody(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(body: LoginBody) -> dict:
    db = get_db()
    docs = db.collection("admins").where("email", "==", body.email).limit(1).get()

    if not docs:
        raise HTTPException(401, "Invalid email or password")

    admin_doc = docs[0]
    data = admin_doc.to_dict()

    if not hmac.compare_digest(data.get("passwordHash", ""), hash_password(body.password)):
        raise HTTPException(401, "Invalid email or password")

    uid = admin_doc.id
    token = fb_auth.create_custom_token(uid)

    return {
        "token": token.decode() if isinstance(token, bytes) else token,
        "uid": uid,
        "email": data["email"],
        "displayName": data.get("displayName", "Admin"),
    }
