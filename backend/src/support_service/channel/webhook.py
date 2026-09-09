"""Webhook endpoints — Gupshup delivers inbound messages and receipts here.

Stubs for now: validate the shared secret and return 200. The full
orchestration (dedupe -> normalize -> route -> respond) is wired in Task 7,
once conversation routing and tickets exist.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Query, Response

router = APIRouter(prefix="/webhook", tags=["webhook"])


def _check_secret(secret: str | None) -> bool:
    expected = os.environ.get("WEBHOOK_SECRET", "")
    if not expected:
        return True
    return secret == expected


@router.post("/gupshup")
def inbound(secret: str | None = Query(None)) -> Response:
    """Receive an inbound WhatsApp message from Gupshup."""
    if not _check_secret(secret):
        return Response(status_code=401)
    return Response(status_code=200)


@router.post("/gupshup/status")
def receipt(secret: str | None = Query(None)) -> Response:
    """Receive a delivery receipt from Gupshup."""
    if not _check_secret(secret):
        return Response(status_code=401)
    return Response(status_code=200)
