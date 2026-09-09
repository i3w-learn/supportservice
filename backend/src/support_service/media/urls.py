# backend/src/support_service/media/urls.py
"""Signed URLs for the dashboard to read attachments (§9)."""

from __future__ import annotations

import os
from datetime import timedelta

from firebase_admin import storage

from support_service.firestore import get_db


def get_signed_url(message_id: str) -> str | None:
    db = get_db()
    results = db.collection_group("messages").where("messageId", "==", message_id).limit(1).get()

    if not results:
        return None

    data = results[0].to_dict()
    attachment = data.get("attachment", {})
    if attachment.get("state") != "stored":
        return None

    storage_path = attachment.get("storagePath")
    if not storage_path:
        return None

    bucket = storage.bucket(os.environ.get("STORAGE_BUCKET"))
    blob = bucket.blob(storage_path)
    url = blob.generate_signed_url(expiration=timedelta(minutes=15))
    return url
