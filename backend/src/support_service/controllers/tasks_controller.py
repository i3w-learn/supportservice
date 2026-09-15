"""Cloud Tasks callbacks (see task_service). Called by our own queue only."""

from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from support_service.models import SlaState
from support_service.services.channel_service import finish_idle_session
from support_service.services.media_service import MediaNotReady, fetch_attachment
from support_service.services.task_service import SECRET_HEADER
from support_service.services.ticket_service import check_sla


def _require_secret(secret: str | None = Header(None, alias=SECRET_HEADER)) -> None:
    expected = os.environ.get("WEBHOOK_SECRET", "")
    if not expected or not secret or not hmac.compare_digest(secret, expected):
        raise HTTPException(401)


router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(_require_secret)])


class MediaTask(BaseModel):
    wa_number: str
    message_id: str


class IdleTask(BaseModel):
    wa_number: str


class SlaTask(BaseModel):
    ticket_id: str


@router.post("/media")
def media_task(body: MediaTask) -> dict[str, str]:
    try:
        state = fetch_attachment(body.wa_number, body.message_id)
    except MediaNotReady as exc:
        # Any non-2xx response makes Cloud Tasks retry with backoff.
        raise HTTPException(503, "Download failed, will retry") from exc
    return {"state": state}


@router.post("/idle")
def idle_task(body: IdleTask) -> dict[str, str | None]:
    return {"ticket_id": finish_idle_session(body.wa_number)}


@router.post("/sla")
def sla_task(body: SlaTask) -> dict[str, SlaState | None]:
    return {"sla_state": check_sla(body.ticket_id)}
