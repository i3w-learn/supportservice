"""Media attachments: fetch from Gupshup into Cloud Storage, signed URLs (§4.1, §9)."""

from __future__ import annotations

import os
from datetime import timedelta

import httpx
from firebase_admin import storage

from support_service.models import AttachmentState
from support_service.repositories.base import get_db, to_firestore
from support_service.repositories.message_repository import find_by_message_id, pending_attachments

MAX_ATTEMPTS = 5


def fetch_pending_media() -> int:
    """Fetch pending attachments from Gupshup and store in Cloud Storage (§4.1 step 7)."""
    db = get_db()
    bucket = storage.bucket(os.environ.get("STORAGE_BUCKET"))

    pending = pending_attachments(db, limit=20).get()

    fetched = 0
    api_key = os.environ.get("GUPSHUP_API_KEY", "")
    app_id = os.environ.get("GUPSHUP_APP_NAME", "")

    for doc in pending:
        data = doc.to_dict()
        attachment = data.get("attachment", {})
        attempts = attachment.get("attempts", 0)

        if attempts >= MAX_ATTEMPTS:
            doc.reference.update({"attachment.state": "failed"})
            continue

        media_id = attachment.get("mediaId")
        if not media_id:
            doc.reference.update(
                {
                    "attachment.state": "failed",
                    "attachment.attempts": attempts + 1,
                }
            )
            continue

        try:
            response = httpx.get(
                f"https://api.gupshup.io/wa/api/v1/msg/{app_id}/media/{media_id}",
                headers={"apikey": api_key},
                timeout=30.0,
            )
            response.raise_for_status()
        except Exception:
            doc.reference.update({"attachment.attempts": attempts + 1})
            continue

        wa_number = doc.reference.parent.parent.id
        message_id = doc.id
        path = f"attachments/{wa_number}/{message_id}"
        mime = attachment.get("mimeType", "application/octet-stream")

        blob = bucket.blob(path)
        blob.upload_from_string(response.content, content_type=mime)

        doc.reference.update(
            to_firestore(
                {
                    "attachment.state": AttachmentState.STORED,
                    "attachment.storage_path": path,
                    "attachment.size_bytes": len(response.content),
                    "attachment.attempts": attempts + 1,
                }
            )
        )
        fetched += 1

    return fetched


def get_signed_url(message_id: str) -> str | None:
    """Signed URL for the dashboard to read an attachment (§9)."""
    db = get_db()
    doc = find_by_message_id(db, message_id)
    if doc is None:
        return None

    data = doc.to_dict()
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
