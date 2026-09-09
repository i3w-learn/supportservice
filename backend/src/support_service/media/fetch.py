# backend/src/support_service/media/fetch.py
"""Fetch pending attachments from Gupshup and store in Cloud Storage (§4.1 step 7)."""

from __future__ import annotations

import os

import httpx
from firebase_admin import storage

from support_service.firestore import get_db, to_firestore
from support_service.models import AttachmentState

MAX_ATTEMPTS = 5


def fetch_pending_media() -> int:
    db = get_db()
    bucket = storage.bucket(os.environ.get("STORAGE_BUCKET"))

    pending = (
        db.collection_group("messages")
        .where("attachment.state", "==", "pending")
        .order_by("createdAt")
        .limit(20)
        .get()
    )

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
