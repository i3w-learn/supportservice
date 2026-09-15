"""Media attachments: fetch from Gupshup into Cloud Storage, signed URLs (§4.1, §9)."""

from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import Any
from urllib.parse import urlparse

import google.auth
import httpx
from firebase_admin import storage
from google.auth.transport.requests import Request

from support_service.models import AttachmentState
from support_service.repositories.base import get_db, to_firestore
from support_service.repositories.contact_repository import contact_messages
from support_service.repositories.message_repository import find_by_message_id
from support_service.services import task_service

MAX_ATTEMPTS = 5

log = logging.getLogger(__name__)
_signing_credentials: Any = None


class MediaNotReady(Exception):
    """The download failed but attempts remain, so the caller should retry."""


def fetch_attachment(wa_number: str, message_id: str) -> str:
    """Copy one inbound photo, video or file into Cloud Storage (§4.1 step 7).

    Returns the attachment's final state. Safe to run twice: anything no
    longer pending is left alone.
    """
    db = get_db()
    ref = contact_messages(db, wa_number).document(message_id)
    snap = ref.get()
    attachment = (snap.to_dict() or {}).get("attachment") if snap.exists else None
    if not attachment:
        return "missing"
    if attachment.get("state") != AttachmentState.PENDING:
        return attachment["state"]

    url = attachment.get("mediaUrl") or ""
    # The URL comes from the webhook body, so only ever fetch from Gupshup.
    if not _is_gupshup(url):
        log.warning("Attachment %s has no usable Gupshup URL", message_id)
        ref.update({"attachment.state": AttachmentState.FAILED})
        return AttachmentState.FAILED

    attempts = attachment.get("attempts", 0) + 1
    try:
        response = httpx.get(url, timeout=60.0, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("Download of %s failed (attempt %d): %s", message_id, attempts, exc)
        if attempts >= MAX_ATTEMPTS:
            ref.update(
                {"attachment.state": AttachmentState.FAILED, "attachment.attempts": attempts}
            )
            return AttachmentState.FAILED
        ref.update({"attachment.attempts": attempts})
        raise MediaNotReady(message_id) from exc

    path = f"attachments/{wa_number}/{message_id}"
    mime = attachment.get("mimeType") or response.headers.get(
        "content-type", "application/octet-stream"
    )
    bucket = storage.bucket(os.environ.get("STORAGE_BUCKET"))
    bucket.blob(path).upload_from_string(response.content, content_type=mime)

    ref.update(
        to_firestore(
            {
                "attachment.state": AttachmentState.STORED,
                "attachment.storage_path": path,
                "attachment.size_bytes": len(response.content),
                "attachment.attempts": attempts,
            }
        )
    )
    return AttachmentState.STORED


def _is_gupshup(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    return parsed.scheme == "https" and (host == "gupshup.io" or host.endswith(".gupshup.io"))


def requeue_attachment(message_id: str) -> bool:
    """Put a failed or stuck download back in the queue. False if nothing to retry."""
    doc = find_by_message_id(get_db(), message_id)
    attachment = (doc.to_dict() or {}).get("attachment") if doc else None
    if doc is None or not attachment or attachment.get("state") == AttachmentState.STORED:
        return False

    doc.reference.update({"attachment.state": AttachmentState.PENDING, "attachment.attempts": 0})
    task_service.enqueue(
        "/tasks/media", {"wa_number": doc.reference.parent.parent.id, "message_id": doc.id}
    )
    return True


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
    email, token = _signer()
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=15),
        service_account_email=email,
        access_token=token,
    )


def _signer() -> tuple[str | None, str | None]:
    """Cloud Run's credentials carry no private key, so sign through the IAM
    API as the service account instead (it has Service Account Token Creator)."""
    global _signing_credentials
    if _signing_credentials is None:
        _signing_credentials, _ = google.auth.default()
    if not _signing_credentials.valid:
        _signing_credentials.refresh(Request())

    email = getattr(_signing_credentials, "service_account_email", None)
    if not email:
        return None, None
    return email, _signing_credentials.token
