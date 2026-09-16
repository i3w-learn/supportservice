# Support Service Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the 5 empty backend modules (channel, tickets, media, admin_api, jobs), seed Firestore, and wire the dashboard to real data — completing the support system described in the design doc.

**Architecture:** Modular monolith on FastAPI. Each module is a Python package under `backend/src/support_service/`. Modules communicate through normalized domain types in `models.py`. The `channel` module is the only one that touches Gupshup. Firestore is accessed via `firebase-admin` (sync client). The dashboard reads Firestore directly via client SDK; all writes go through the REST API.

**Tech Stack:** Python 3.12, FastAPI, firebase-admin, httpx, python-ulid, Pydantic v2, pytest + hypothesis. Frontend: React 18, Vite, TypeScript, Firebase JS SDK.

**Spec:** `support-system-design.md` (root of repo) — the design doc is the spec. `gupshup-integration-guide.md` covers Gupshup API details.

## Global Constraints

- Python 3.12, pinned via `.python-version`. Dependencies via `uv` with committed lockfile.
- Sync `def` handlers only — the Firestore client is synchronous. FastAPI threadpools them.
- `firebase-admin` is the only Firestore/Auth/Storage dependency. Do not add `google-cloud-firestore` or `google-cloud-storage` separately.
- All domain types live in `models.py`. Modules import from there, never from each other's internals.
- `conversation` and `tickets` never import Gupshup types — only normalized shapes.
- Ruff for lint+format (line-length 100). Pyright for type checking.
- Tests marked `@pytest.mark.firestore` need the emulator. Pure tests run without it.
- Firestore field names use camelCase (matching the JS SDK convention). Python models use snake_case. Conversion happens at the Firestore boundary.

---

### Task 1: Firestore helpers — read/write with camelCase conversion

The Firestore layer that every other module depends on. Handles the snake_case ↔ camelCase conversion in one place.

**Files:**
- Create: `backend/src/support_service/firestore.py`
- Test: `backend/tests/test_firestore.py`

**Interfaces:**
- Produces: `get_doc(collection, doc_id) -> dict | None`, `set_doc(collection, doc_id, data)`, `update_doc(collection, doc_id, data)`, `run_transaction(callback)`, `get_db() -> firestore.Client`, `to_firestore(data: dict) -> dict`, `from_firestore(data: dict) -> dict`

- [ ] **Step 1: Write the failing test for camelCase conversion**

```python
# backend/tests/test_firestore.py
from support_service.firestore import to_firestore, from_firestore


def test_to_firestore_converts_snake_to_camel() -> None:
    assert to_firestore({"open_ticket_ids": ["TKT-1"], "wa_number": "91123"}) == {
        "openTicketIds": ["TKT-1"],
        "waNumber": "91123",
    }


def test_from_firestore_converts_camel_to_snake() -> None:
    assert from_firestore({"openTicketIds": ["TKT-1"], "waNumber": "91123"}) == {
        "open_ticket_ids": ["TKT-1"],
        "wa_number": "91123",
    }


def test_nested_dicts_are_converted() -> None:
    assert to_firestore({"session": {"last_activity_at": 123}}) == {
        "session": {"lastActivityAt": 123},
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_firestore.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Implement the Firestore helpers**

```python
# backend/src/support_service/firestore.py
"""Firestore access. One place for the camelCase boundary and the db client."""

from __future__ import annotations

import re
from typing import Any

import firebase_admin
from firebase_admin import firestore

_app: firebase_admin.App | None = None


def get_db() -> firestore.firestore.Client:
    global _app
    if _app is None:
        _app = firebase_admin.initialize_app()
    return firestore.client(_app)


def _to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _to_snake(name: str) -> str:
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()


def _convert_keys(data: Any, fn: Any) -> Any:
    if isinstance(data, dict):
        return {fn(k): _convert_keys(v, fn) for k, v in data.items()}
    if isinstance(data, list):
        return [_convert_keys(item, fn) for item in data]
    return data


def to_firestore(data: dict[str, Any]) -> dict[str, Any]:
    return _convert_keys(data, _to_camel)


def from_firestore(data: dict[str, Any]) -> dict[str, Any]:
    return _convert_keys(data, _to_snake)


def get_doc(collection: str, doc_id: str) -> dict[str, Any] | None:
    doc = get_db().collection(collection).document(doc_id).get()
    return from_firestore(doc.to_dict()) if doc.exists else None


def set_doc(collection: str, doc_id: str, data: dict[str, Any]) -> None:
    get_db().collection(collection).document(doc_id).set(to_firestore(data))


def update_doc(collection: str, doc_id: str, data: dict[str, Any]) -> None:
    get_db().collection(collection).document(doc_id).update(to_firestore(data))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_firestore.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/support_service/firestore.py backend/tests/test_firestore.py
git commit -m "feat: add Firestore helpers with camelCase conversion"
```

---

### Task 2: Channel module — Gupshup send + normalize + webhook

The adapter between Gupshup's API and our normalized domain types. This is the only module that knows Gupshup exists.

**Files:**
- Create: `backend/src/support_service/channel/normalize.py`
- Create: `backend/src/support_service/channel/send.py`
- Create: `backend/src/support_service/channel/webhook.py`
- Modify: `backend/src/support_service/channel/__init__.py`
- Modify: `backend/src/support_service/main.py`
- Test: `backend/tests/channel/test_normalize.py`
- Test: `backend/tests/channel/test_send.py`

**Interfaces:**
- Consumes: `InboundMessage`, `Attachment`, `MessageType` from `models.py`; `Reply`, `SendText`, `SendList`, `SendButtons` from `conversation/steps.py`
- Produces: `normalize(payload: dict) -> InboundMessage`, `send_text(to: str, text: str) -> str`, `send_list(to: str, body: str, button_title: str, rows: list[Row]) -> str`, `send_buttons(to: str, body: str, buttons: list[Row]) -> str`, `send_template(to: str, template_name: str, language: str, params: list[str]) -> str`, `send_reply(to: str, reply: Reply) -> str`, `webhook_router` (FastAPI APIRouter)

- [ ] **Step 1: Write failing test for payload normalization**

```python
# backend/tests/channel/__init__.py
```

```python
# backend/tests/channel/test_normalize.py
from support_service.channel.normalize import normalize
from support_service.models import AttachmentState, MessageType


def test_text_message() -> None:
    payload = {
        "app": "TestApp",
        "timestamp": 1725888000000,
        "version": 2,
        "type": "message",
        "payload": {
            "id": "wamid.ABC123",
            "source": "919876543210",
            "type": "text",
            "payload": {"text": "Hello"},
            "sender": {"phone": "919876543210", "name": "Test"},
        },
    }
    msg = normalize(payload)
    assert msg.provider_message_id == "wamid.ABC123"
    assert msg.wa_number == "919876543210"
    assert msg.type == MessageType.TEXT
    assert msg.text == "Hello"
    assert msg.attachment is None


def test_list_reply() -> None:
    payload = {
        "app": "TestApp",
        "timestamp": 1725888000000,
        "version": 2,
        "type": "message",
        "payload": {
            "id": "wamid.ABC124",
            "source": "919876543210",
            "type": "list_reply",
            "payload": {
                "title": "Anganwadi VR",
                "id": "product-picker",
                "postbackText": "anganwadi-vr",
            },
            "sender": {"phone": "919876543210", "name": "Test"},
        },
    }
    msg = normalize(payload)
    assert msg.type == MessageType.INTERACTIVE
    assert msg.reply_id == "anganwadi-vr"
    assert msg.text == "Anganwadi VR"


def test_button_reply() -> None:
    payload = {
        "app": "TestApp",
        "timestamp": 1725888000000,
        "version": 2,
        "type": "message",
        "payload": {
            "id": "wamid.ABC125",
            "source": "919876543210",
            "type": "button_reply",
            "payload": {"title": "Done", "id": "done"},
            "sender": {"phone": "919876543210", "name": "Test"},
        },
    }
    msg = normalize(payload)
    assert msg.type == MessageType.INTERACTIVE
    assert msg.reply_id == "done"


def test_image_message() -> None:
    payload = {
        "app": "TestApp",
        "timestamp": 1725888000000,
        "version": 2,
        "type": "message",
        "payload": {
            "id": "wamid.ABC126",
            "source": "919876543210",
            "type": "image",
            "payload": {
                "url": "https://media.example.com/img.jpg",
                "mediaId": "76534618",
                "caption": "See this",
            },
            "sender": {"phone": "919876543210", "name": "Test"},
        },
    }
    msg = normalize(payload)
    assert msg.type == MessageType.IMAGE
    assert msg.text == "See this"
    assert msg.attachment is not None
    assert msg.attachment.state == AttachmentState.PENDING
    assert msg.attachment.mime_type == "image/jpeg"


def test_reply_context() -> None:
    payload = {
        "app": "TestApp",
        "timestamp": 1725888000000,
        "version": 2,
        "type": "message",
        "payload": {
            "id": "wamid.ABC127",
            "source": "919876543210",
            "type": "text",
            "payload": {"text": "Still broken"},
            "context": {"id": "wamid.OUT999", "gsId": "gs-123"},
            "sender": {"phone": "919876543210", "name": "Test"},
        },
    }
    msg = normalize(payload)
    assert msg.context_message_id == "wamid.OUT999"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/channel/test_normalize.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Implement normalize.py**

```python
# backend/src/support_service/channel/normalize.py
"""Turn a Gupshup webhook payload into an InboundMessage.

This is the one file that knows Gupshup's JSON shape. Everything downstream
sees only the normalized InboundMessage from models.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from support_service.models import Attachment, AttachmentState, InboundMessage, MessageType

_TYPE_MAP: dict[str, MessageType] = {
    "text": MessageType.TEXT,
    "image": MessageType.IMAGE,
    "video": MessageType.VIDEO,
    "file": MessageType.DOCUMENT,
    "audio": MessageType.DOCUMENT,
    "list_reply": MessageType.INTERACTIVE,
    "button_reply": MessageType.INTERACTIVE,
    "quick_reply": MessageType.INTERACTIVE,
}

_MEDIA_TYPES = {"image", "video", "file", "audio"}

_MIME_GUESS: dict[str, str] = {
    "image": "image/jpeg",
    "video": "video/mp4",
    "file": "application/octet-stream",
    "audio": "audio/ogg",
}


def normalize(raw: dict[str, Any]) -> InboundMessage:
    payload = raw["payload"]
    inner = payload.get("payload", {})
    gupshup_type = payload["type"]

    msg_type = _TYPE_MAP.get(gupshup_type, MessageType.TEXT)

    text: str | None = None
    reply_id: str | None = None
    attachment: Attachment | None = None
    context_message_id: str | None = None

    if gupshup_type == "text":
        text = inner.get("text")

    elif gupshup_type in ("list_reply", "quick_reply"):
        text = inner.get("title")
        reply_id = inner.get("postbackText") or inner.get("id")

    elif gupshup_type == "button_reply":
        text = inner.get("title")
        reply_id = inner.get("id")

    elif gupshup_type in _MEDIA_TYPES:
        text = inner.get("caption")
        attachment = Attachment(
            state=AttachmentState.PENDING,
            mime_type=inner.get("mimeType") or _MIME_GUESS.get(gupshup_type),
        )

    context = payload.get("context")
    if context:
        context_message_id = context.get("id")

    ts = raw.get("timestamp", 0)
    received_at = datetime.fromtimestamp(ts / 1000, tz=UTC) if ts else datetime.now(UTC)

    return InboundMessage(
        provider_message_id=payload["id"],
        wa_number=payload["source"],
        type=msg_type,
        text=text,
        reply_id=reply_id,
        context_message_id=context_message_id,
        attachment=attachment,
        received_at=received_at,
    )
```

- [ ] **Step 4: Run normalization tests**

Run: `cd backend && uv run pytest tests/channel/test_normalize.py -v`
Expected: PASS

- [ ] **Step 5: Implement send.py**

```python
# backend/src/support_service/channel/send.py
"""Outbound messages to Gupshup. Every send returns the Gupshup messageId."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

from support_service.conversation.steps import Reply, Row, SendButtons, SendList, SendText

API_URL = "https://api.gupshup.io/wa/api/v1/msg"


@dataclass
class GupshupConfig:
    api_key: str
    app_name: str
    source_number: str


def _config() -> GupshupConfig:
    return GupshupConfig(
        api_key=os.environ["GUPSHUP_API_KEY"],
        app_name=os.environ["GUPSHUP_APP_NAME"],
        source_number=os.environ["GUPSHUP_SOURCE_NUMBER"],
    )


def _send(destination: str, message: dict[str, Any]) -> str:
    cfg = _config()
    response = httpx.post(
        API_URL,
        headers={"apikey": cfg.api_key},
        data={
            "channel": "whatsapp",
            "source": cfg.source_number,
            "destination": destination,
            "src.name": cfg.app_name,
            "message": json.dumps(message),
        },
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json().get("messageId", "")


def send_text(to: str, text: str) -> str:
    return _send(to, {"type": "text", "text": text})


def send_list(to: str, body: str, button_title: str, rows: list[Row]) -> str:
    return _send(
        to,
        {
            "type": "list",
            "title": body[:60],
            "body": body,
            "msgid": "list",
            "globalButtons": [{"type": "text", "title": button_title[:20]}],
            "items": [
                {
                    "title": "Options",
                    "options": [
                        {"type": "text", "title": row.label[:24], "postbackText": row.id}
                        for row in rows
                    ],
                }
            ],
        },
    )


def send_buttons(to: str, body: str, buttons: list[Row]) -> str:
    return _send(
        to,
        {
            "type": "quick_reply",
            "msgid": "qr",
            "content": {"type": "text", "text": body},
            "options": [{"type": "text", "title": btn.label[:20]} for btn in buttons],
        },
    )


def send_template(to: str, template_name: str, language: str, params: list[str]) -> str:
    return _send(
        to,
        {
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"policy": "deterministic", "code": language},
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": p} for p in params],
                    }
                ],
            },
        },
    )


def send_reply(to: str, reply: Reply) -> str:
    if isinstance(reply, SendText):
        return send_text(to, reply.body)
    if isinstance(reply, SendList):
        return send_list(to, reply.body, "Choose", list(reply.rows))
    if isinstance(reply, SendButtons):
        return send_buttons(to, reply.body, list(reply.buttons))
    raise ValueError(f"Unknown reply type: {type(reply)}")
```

- [ ] **Step 6: Write test for send_reply dispatching**

```python
# backend/tests/channel/test_send.py
from unittest.mock import patch

from support_service.channel.send import send_reply
from support_service.conversation.steps import Row, SendButtons, SendList, SendText


@patch("support_service.channel.send._send", return_value="msg-001")
def test_send_text_dispatches(mock_send: object) -> None:
    result = send_reply("919876543210", SendText("Hello"))
    assert result == "msg-001"


@patch("support_service.channel.send._send", return_value="msg-002")
def test_send_list_dispatches(mock_send: object) -> None:
    rows = [Row("a", "Option A"), Row("b", "Option B")]
    result = send_reply("919876543210", SendList("Pick one", rows))
    assert result == "msg-002"


@patch("support_service.channel.send._send", return_value="msg-003")
def test_send_buttons_dispatches(mock_send: object) -> None:
    buttons = [Row("done", "Done")]
    result = send_reply("919876543210", SendButtons("Tap when ready", buttons))
    assert result == "msg-003"
```

- [ ] **Step 7: Run send tests**

Run: `cd backend && uv run pytest tests/channel/test_send.py -v`
Expected: PASS

- [ ] **Step 8: Implement webhook.py — the inbound and receipt routers**

```python
# backend/src/support_service/channel/webhook.py
"""Webhook endpoints — Gupshup delivers inbound messages and receipts here."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Query, Request, Response

from support_service.channel.normalize import normalize
from support_service.firestore import get_db, get_doc, set_doc, to_firestore

router = APIRouter(prefix="/webhook", tags=["webhook"])


def _check_secret(secret: str | None) -> bool:
    expected = os.environ.get("WEBHOOK_SECRET", "")
    if not expected:
        return True
    return secret == expected


@router.post("/gupshup")
def inbound(request: Request, secret: str | None = Query(None)) -> Response:
    """Receive an inbound WhatsApp message from Gupshup."""
    if not _check_secret(secret):
        return Response(status_code=401)

    # FastAPI parses JSON for us when we declare the body, but Gupshup
    # sometimes sends form-encoded. Accept raw and parse ourselves.
    import json

    body: dict[str, Any] = {}
    content_type = request.headers.get("content-type", "")
    # We need the raw body synchronously. FastAPI threadpools sync handlers,
    # so we can read it via the underlying scope.
    # Actually — use a dict body param instead. Simpler.
    return Response(status_code=200)


@router.post("/gupshup/status")
def receipt(request: Request, secret: str | None = Query(None)) -> Response:
    """Receive a delivery receipt from Gupshup."""
    if not _check_secret(secret):
        return Response(status_code=401)
    return Response(status_code=200)
```

Note: The webhook handlers are stubs at this point. They validate the secret and return 200. The actual message processing logic (dedupe → normalize → route → respond) is wired in Task 5 after tickets and the orchestration layer exist.

- [ ] **Step 9: Wire the webhook router into main.py and update channel __init__**

```python
# backend/src/support_service/channel/__init__.py
from support_service.channel.normalize import normalize
from support_service.channel.send import (
    send_buttons,
    send_list,
    send_reply,
    send_template,
    send_text,
)
from support_service.channel.webhook import router as webhook_router

__all__ = [
    "normalize",
    "send_buttons",
    "send_list",
    "send_reply",
    "send_template",
    "send_text",
    "webhook_router",
]
```

Add to `main.py`:
```python
from support_service.channel import webhook_router
app.include_router(webhook_router)
```

- [ ] **Step 10: Run all tests**

Run: `cd backend && uv run pytest -m "not firestore" -v`
Expected: All pass including existing conversation tests

- [ ] **Step 11: Commit**

```bash
git add backend/src/support_service/channel/ backend/tests/channel/ backend/src/support_service/main.py
git commit -m "feat: channel module — normalize, send, webhook stub"
```

---

### Task 3: Tickets module — create, transitions, resolution

The core business logic. Ticket creation runs as a Firestore transaction. Status transitions follow the §8 table. Resolution dispatches a WhatsApp message.

**Files:**
- Create: `backend/src/support_service/tickets/create.py`
- Create: `backend/src/support_service/tickets/transitions.py`
- Create: `backend/src/support_service/tickets/resolution.py`
- Modify: `backend/src/support_service/tickets/__init__.py`
- Test: `backend/tests/tickets/test_transitions.py`
- Test: `backend/tests/tickets/test_create.py` (firestore-marked)

**Interfaces:**
- Consumes: `Draft` from `conversation/steps.py`; `TicketStatus`, `EventType` from `models.py`; `get_db`, `to_firestore`, `from_firestore` from `firestore.py`; `send_text`, `send_template` from `channel/send.py`
- Produces: `create_ticket(draft: Draft, contact_ref, wa_number: str) -> str` (returns ticket_id), `change_status(ticket_id: str, to: TicketStatus, actor: str, uid: str | None, note: str | None) -> None`, `resolve_ticket(ticket_id: str, text: str, actor_uid: str) -> None`, `resend_resolution(ticket_id: str) -> None`, `LEGAL_TRANSITIONS: dict[TicketStatus, list[TicketStatus]]`

- [ ] **Step 1: Write failing test for transition validation**

```python
# backend/tests/tickets/__init__.py
```

```python
# backend/tests/tickets/test_transitions.py
import pytest

from support_service.models import TicketStatus
from support_service.tickets.transitions import validate_transition


class TestLegalTransitions:
    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            ("open", "in_progress"),
            ("open", "resolved"),
            ("in_progress", "open"),
            ("in_progress", "resolved"),
            ("resolved", "closed"),
            ("resolved", "in_progress"),
            ("closed", "open"),
        ],
    )
    def test_legal_transitions_pass(self, from_status: str, to_status: str) -> None:
        validate_transition(TicketStatus(from_status), TicketStatus(to_status))

    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            ("open", "closed"),
            ("open", "open"),
            ("in_progress", "closed"),
            ("in_progress", "in_progress"),
            ("resolved", "open"),
            ("resolved", "resolved"),
            ("closed", "closed"),
            ("closed", "in_progress"),
            ("closed", "resolved"),
        ],
    )
    def test_illegal_transitions_raise(self, from_status: str, to_status: str) -> None:
        with pytest.raises(ValueError):
            validate_transition(TicketStatus(from_status), TicketStatus(to_status))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/tickets/test_transitions.py -v`
Expected: FAIL

- [ ] **Step 3: Implement transitions.py**

```python
# backend/src/support_service/tickets/transitions.py
"""Status transition table (§8). Anything not listed here is a 409."""

from support_service.models import TicketStatus

LEGAL: dict[TicketStatus, list[TicketStatus]] = {
    TicketStatus.OPEN: [TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED],
    TicketStatus.IN_PROGRESS: [TicketStatus.OPEN, TicketStatus.RESOLVED],
    TicketStatus.RESOLVED: [TicketStatus.CLOSED, TicketStatus.IN_PROGRESS],
    TicketStatus.CLOSED: [TicketStatus.OPEN],
}


def validate_transition(from_status: TicketStatus, to_status: TicketStatus) -> None:
    if to_status not in LEGAL.get(from_status, []):
        raise ValueError(f"{from_status} → {to_status} is not a legal transition")
```

- [ ] **Step 4: Run transition tests**

Run: `cd backend && uv run pytest tests/tickets/test_transitions.py -v`
Expected: PASS

- [ ] **Step 5: Implement create.py — ticket creation transaction**

```python
# backend/src/support_service/tickets/create.py
"""Ticket creation — one Firestore transaction (§8)."""

from __future__ import annotations

from datetime import UTC, datetime

from google.cloud.firestore_v1 import transaction as fs_transaction

from support_service.conversation.steps import Draft
from support_service.firestore import get_db, to_firestore
from support_service.models import EventType, SlaState, TicketStatus


def _ticket_id(date: datetime, seq: int) -> str:
    return f"TKT-{date.strftime('%Y%m%d')}-{seq:04d}"


def create_ticket(draft: Draft, wa_number: str, *, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    db = get_db()

    @fs_transaction.transactional
    def _txn(txn: fs_transaction.Transaction) -> str:
        counter_ref = db.collection("counters").document(now.strftime("%Y%m%d"))
        counter_snap = counter_ref.get(transaction=txn)
        seq = (counter_snap.to_dict() or {}).get("seq", 0) + 1

        ticket_id = _ticket_id(now, seq)
        ticket_ref = db.collection("tickets").document(ticket_id)
        contact_ref = db.collection("contacts").document(wa_number)

        contact_snap = contact_ref.get(transaction=txn)
        contact_data = contact_snap.to_dict() or {}
        open_ids: list[str] = contact_data.get("openTicketIds", [])

        for existing_id in open_ids:
            existing = db.collection("tickets").document(existing_id).get(transaction=txn)
            if existing.exists and existing.to_dict().get("serviceId") == draft.service_id:
                raise ValueError(f"Already open for this product: {existing_id}")

        config_service = db.collection("services").document(draft.service_id).get()
        service_data = config_service.to_dict() or {}
        service_name = service_data.get("name", {}).get(draft.language, draft.service_id)
        category_label = draft.category_id
        for cat in service_data.get("categories", []):
            if cat.get("id") == draft.category_id:
                category_label = cat.get("label", {}).get(draft.language, draft.category_id)
                break

        ticket_data = to_firestore({
            "wa_number": wa_number,
            "contact_name": draft.display_name,
            "centre_name": draft.centre_name,
            "service_id": draft.service_id,
            "service_name": service_name,
            "category_id": draft.category_id,
            "category_label": category_label,
            "language": draft.language,
            "description": draft.description,
            "attachment_count": 0,
            "status": TicketStatus.OPEN,
            "sla_state": SlaState.OK,
            "resolution": None,
            "created_at": now,
            "updated_at": now,
            "first_response_at": None,
            "resolved_at": None,
            "closed_at": None,
        })

        event_data = to_firestore({
            "type": EventType.CREATED,
            "from": None,
            "to": None,
            "actor": "bot",
            "actor_uid": None,
            "note": None,
            "at": now,
        })

        txn.set(counter_ref, {"seq": seq})
        txn.set(ticket_ref, ticket_data)
        txn.set(ticket_ref.collection("events").document(), event_data)
        txn.update(contact_ref, {
            "openTicketIds": open_ids + [ticket_id],
            "session": None,
            "updatedAt": now,
        })

        return ticket_id

    return _txn(db.transaction())
```

- [ ] **Step 6: Implement resolution.py**

```python
# backend/src/support_service/tickets/resolution.py
"""Send a resolution and manage the resolved/closed lifecycle (§4.3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from support_service.channel.send import send_template, send_text
from support_service.firestore import get_db, get_doc, to_firestore, update_doc
from support_service.models import EventType, ProviderStatus, TicketStatus
from support_service.tickets.transitions import validate_transition

TEMPLATE_NAME = "resolution_notification"


def resolve_ticket(ticket_id: str, text: str, actor_uid: str) -> str:
    ticket = get_doc("tickets", ticket_id)
    if not ticket:
        raise ValueError(f"Ticket {ticket_id} not found")

    current = TicketStatus(ticket["status"])
    validate_transition(current, TicketStatus.RESOLVED)

    wa_number = ticket["wa_number"]
    contact = get_doc("contacts", wa_number)
    last_inbound = contact.get("last_inbound_at") if contact else None

    now = datetime.now(UTC)
    window = timedelta(hours=24)
    inside_window = last_inbound and (now - last_inbound) < window

    if inside_window:
        message_id = send_text(wa_number, text)
        sent_via = "freeform"
    else:
        language = ticket.get("language", "en")
        contact_name = ticket.get("contact_name", "")
        params = [contact_name, ticket_id, text]
        message_id = send_template(wa_number, TEMPLATE_NAME, language, params)
        sent_via = "template"

    db = get_db()
    ticket_ref = db.collection("tickets").document(ticket_id)
    ticket_ref.update(to_firestore({
        "status": TicketStatus.RESOLVED,
        "resolved_at": now,
        "updated_at": now,
        "resolution": {
            "text": text,
            "sent_at": now,
            "delivery_state": ProviderStatus.QUEUED,
            "attempts": 1,
        },
    }))

    ticket_ref.collection("events").document().set(to_firestore({
        "type": EventType.RESOLUTION_SENT,
        "from": current,
        "to": TicketStatus.RESOLVED,
        "actor": "admin",
        "actor_uid": actor_uid,
        "note": f"Sent as {sent_via}",
        "at": now,
    }))

    return message_id
```

- [ ] **Step 7: Update tickets __init__**

```python
# backend/src/support_service/tickets/__init__.py
from support_service.tickets.create import create_ticket
from support_service.tickets.resolution import resolve_ticket
from support_service.tickets.transitions import LEGAL, validate_transition

__all__ = ["LEGAL", "create_ticket", "resolve_ticket", "validate_transition"]
```

- [ ] **Step 8: Run all unit tests**

Run: `cd backend && uv run pytest -m "not firestore" -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/src/support_service/tickets/ backend/tests/tickets/
git commit -m "feat: tickets module — create, transitions, resolution"
```

---

### Task 4: Admin API — REST endpoints with token verification

The REST surface that the dashboard writes to. Every route checks the Firebase ID token and admin allowlist membership.

**Files:**
- Create: `backend/src/support_service/admin_api/auth.py`
- Create: `backend/src/support_service/admin_api/routes.py`
- Modify: `backend/src/support_service/admin_api/__init__.py`
- Modify: `backend/src/support_service/main.py`
- Test: `backend/tests/admin_api/test_routes.py`

**Interfaces:**
- Consumes: `validate_transition`, `resolve_ticket` from `tickets`; `get_doc`, `update_doc` from `firestore.py`; `firebase_admin.auth` for token verification
- Produces: `admin_router` (FastAPI APIRouter), `get_admin_uid(request) -> str` dependency

- [ ] **Step 1: Implement auth.py — token verification + admin check**

```python
# backend/src/support_service/admin_api/auth.py
"""Firebase ID token verification and admin allowlist check (§9)."""

from __future__ import annotations

from functools import lru_cache
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
    except Exception:
        raise HTTPException(401, "Invalid token")

    uid = decoded["uid"]
    if not _is_admin(uid):
        raise HTTPException(403, "Not an admin")

    return uid
```

- [ ] **Step 2: Implement routes.py**

```python
# backend/src/support_service/admin_api/routes.py
"""Admin REST endpoints (§9)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from support_service.admin_api.auth import get_admin_uid
from support_service.firestore import get_db, get_doc, to_firestore, update_doc
from support_service.models import EventType, TicketStatus
from support_service.tickets.resolution import resolve_ticket
from support_service.tickets.transitions import validate_transition

router = APIRouter(prefix="/tickets", tags=["admin"], dependencies=[Depends(get_admin_uid)])


class StatusBody(BaseModel):
    to: TicketStatus
    note: str | None = None


class ResolutionBody(BaseModel):
    text: str


class NoteBody(BaseModel):
    text: str


@router.patch("/{ticket_id}/status")
def change_status(
    ticket_id: str, body: StatusBody, uid: str = Depends(get_admin_uid)
) -> dict[str, str]:
    ticket = get_doc("tickets", ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    current = TicketStatus(ticket["status"])
    try:
        validate_transition(current, body.to)
    except ValueError as exc:
        raise HTTPException(409, str(exc))

    now = datetime.now(UTC)
    updates: dict = {
        "status": body.to,
        "updated_at": now,
    }
    if body.to == TicketStatus.IN_PROGRESS and ticket.get("first_response_at") is None:
        updates["first_response_at"] = now

    update_doc("tickets", ticket_id, updates)

    db = get_db()
    db.collection("tickets").document(ticket_id).collection("events").document().set(
        to_firestore({
            "type": EventType.STATUS_CHANGED,
            "from": current,
            "to": body.to,
            "actor": "admin",
            "actor_uid": uid,
            "note": body.note,
            "at": now,
        })
    )
    return {"status": "ok"}


@router.post("/{ticket_id}/resolution")
def send_resolution(
    ticket_id: str, body: ResolutionBody, uid: str = Depends(get_admin_uid)
) -> dict[str, str]:
    try:
        message_id = resolve_ticket(ticket_id, body.text, uid)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except Exception:
        raise HTTPException(502, "Send failed")
    return {"status": "ok", "messageId": message_id}


@router.post("/{ticket_id}/notes")
def add_note(
    ticket_id: str, body: NoteBody, uid: str = Depends(get_admin_uid)
) -> dict[str, str]:
    ticket = get_doc("tickets", ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    now = datetime.now(UTC)
    db = get_db()
    db.collection("tickets").document(ticket_id).collection("events").document().set(
        to_firestore({
            "type": EventType.NOTE,
            "from": None,
            "to": None,
            "actor": "admin",
            "actor_uid": uid,
            "note": body.text,
            "at": now,
        })
    )
    update_doc("tickets", ticket_id, {"updated_at": now})
    return {"status": "ok"}


@router.post("/{ticket_id}/resend")
def resend_resolution(
    ticket_id: str, uid: str = Depends(get_admin_uid)
) -> dict[str, str]:
    ticket = get_doc("tickets", ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    resolution = ticket.get("resolution")
    if not resolution or ticket["status"] != TicketStatus.RESOLVED:
        raise HTTPException(409, "Nothing to resend")

    if resolution.get("delivery_state") != "failed":
        raise HTTPException(409, "Delivery did not fail")

    try:
        message_id = resolve_ticket(ticket_id, resolution["text"], uid)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except Exception:
        raise HTTPException(502, "Send failed")
    return {"status": "ok", "messageId": message_id}
```

- [ ] **Step 3: Create the attachment URL endpoint**

Add to `routes.py`:
```python
from support_service.media import get_signed_url

@router.get("/attachments/{message_id}/url", tags=["admin"])
def attachment_url(message_id: str, uid: str = Depends(get_admin_uid)) -> dict[str, str]:
    url = get_signed_url(message_id)
    if not url:
        raise HTTPException(404, "Attachment not found or not stored yet")
    return {"url": url}
```

Note: `get_signed_url` is implemented in Task 5 (media module). This import will fail until then — that is expected. The attachment endpoint is wired last.

- [ ] **Step 4: Wire admin router into main.py**

Add to `main.py`:
```python
from support_service.admin_api.routes import router as admin_router
app.include_router(admin_router)
```

- [ ] **Step 5: Update admin_api __init__**

```python
# backend/src/support_service/admin_api/__init__.py
from support_service.admin_api.routes import router as admin_router

__all__ = ["admin_router"]
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/support_service/admin_api/ backend/src/support_service/main.py
git commit -m "feat: admin API — status, resolution, notes, resend"
```

---

### Task 5: Media module — fetch, store, signed URLs

Downloads media from Gupshup, stores in Cloud Storage, mints signed URLs for the dashboard.

**Files:**
- Create: `backend/src/support_service/media/fetch.py`
- Create: `backend/src/support_service/media/urls.py`
- Modify: `backend/src/support_service/media/__init__.py`
- Test: `backend/tests/media/test_urls.py`

**Interfaces:**
- Consumes: `get_db`, `update_doc` from `firestore.py`; `firebase_admin.storage`
- Produces: `fetch_pending_media() -> int` (returns count fetched), `get_signed_url(message_id: str) -> str | None`

- [ ] **Step 1: Implement fetch.py**

```python
# backend/src/support_service/media/fetch.py
"""Fetch pending attachments from Gupshup and store in Cloud Storage (§4.1 step 7)."""

from __future__ import annotations

import os
from datetime import UTC, datetime

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
    app_id = os.environ.get("GUPSHUP_APP_ID", "")

    for doc in pending:
        data = doc.to_dict()
        attachment = data.get("attachment", {})
        attempts = attachment.get("attempts", 0)

        if attempts >= MAX_ATTEMPTS:
            doc.reference.update({"attachment.state": "failed"})
            continue

        media_id = attachment.get("mediaId")
        if not media_id:
            doc.reference.update({
                "attachment.state": "failed",
                "attachment.attempts": attempts + 1,
            })
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

        doc.reference.update(to_firestore({
            "attachment.state": AttachmentState.STORED,
            "attachment.storage_path": path,
            "attachment.size_bytes": len(response.content),
            "attachment.attempts": attempts + 1,
        }))
        fetched += 1

    return fetched
```

- [ ] **Step 2: Implement urls.py**

```python
# backend/src/support_service/media/urls.py
"""Signed URLs for the dashboard to read attachments (§9)."""

from __future__ import annotations

import os
from datetime import timedelta

from firebase_admin import storage

from support_service.firestore import get_db


def get_signed_url(message_id: str) -> str | None:
    db = get_db()
    results = (
        db.collection_group("messages")
        .where("messageId", "==", message_id)
        .limit(1)
        .get()
    )

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
```

- [ ] **Step 3: Update media __init__**

```python
# backend/src/support_service/media/__init__.py
from support_service.media.fetch import fetch_pending_media
from support_service.media.urls import get_signed_url

__all__ = ["fetch_pending_media", "get_signed_url"]
```

- [ ] **Step 4: Commit**

```bash
git add backend/src/support_service/media/
git commit -m "feat: media module — fetch pending, signed URLs"
```

---

### Task 6: Jobs module — the two crons

The 2-minute cron (media fetch + idle description sessions) and the hourly sweep (SLA flagging, resolution retries, abandoned sessions, recentlyClosed pruning).

**Files:**
- Create: `backend/src/support_service/jobs/media_pass.py`
- Create: `backend/src/support_service/jobs/sweep.py`
- Create: `backend/src/support_service/jobs/routes.py`
- Modify: `backend/src/support_service/jobs/__init__.py`
- Modify: `backend/src/support_service/main.py`
- Test: `backend/tests/jobs/test_sweep_logic.py`

**Interfaces:**
- Consumes: `fetch_pending_media` from `media`; `finish_idle` from `conversation/steps.py`; `create_ticket` from `tickets`; `send_reply` from `channel`; `get_db`, `to_firestore` from `firestore.py`; `Settings` from `config/models.py`
- Produces: `jobs_router` (FastAPI APIRouter)

- [ ] **Step 1: Implement media_pass.py — 2-minute cron**

```python
# backend/src/support_service/jobs/media_pass.py
"""2-minute cron: fetch pending media and finish idle description sessions (§7, §11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from support_service.channel.send import send_text
from support_service.config.defaults import seed
from support_service.conversation.steps import finish_idle
from support_service.firestore import get_db, from_firestore, to_firestore
from support_service.media import fetch_pending_media
from support_service.models import Language, Session
from support_service.tickets.create import create_ticket


def run_media_pass() -> dict[str, int]:
    media_count = fetch_pending_media()
    idle_count = _finish_idle_sessions()
    return {"media_fetched": media_count, "idle_finished": idle_count}


def _finish_idle_sessions() -> int:
    db = get_db()
    config = seed()
    idle_threshold = timedelta(seconds=config.settings.description_idle_seconds)
    cutoff = datetime.now(UTC) - idle_threshold

    idle = (
        db.collection("contacts")
        .where("session.step", "==", "description")
        .where("session.lastActivityAt", "<", cutoff)
        .limit(20)
        .get()
    )

    count = 0
    for doc in idle:
        data = from_firestore(doc.to_dict())
        session_data = data.get("session")
        if not session_data:
            continue

        session = Session(**session_data)
        draft = finish_idle(session)
        if draft is None:
            doc.reference.update({"session": None, "updatedAt": datetime.now(UTC)})
            continue

        try:
            ticket_id = create_ticket(draft, data["wa_number"])
            language = Language(draft.language) if draft.language else Language.EN
            confirmation = config.text("ticket_created", language).format(ticket_id=ticket_id)
            send_text(data["wa_number"], confirmation)
            count += 1
        except Exception:
            doc.reference.update({"session": None, "updatedAt": datetime.now(UTC)})

    return count
```

- [ ] **Step 2: Implement sweep.py — hourly cron**

```python
# backend/src/support_service/jobs/sweep.py
"""Hourly sweep: SLA flagging, resolution retries, abandoned sessions, pruning (§11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from support_service.config.defaults import seed
from support_service.firestore import get_db, to_firestore
from support_service.models import EventType, SlaState, TicketStatus


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
        doc.reference.collection("events").document().set(to_firestore({
            "type": EventType.SLA_FLAGGED,
            "from": current_sla,
            "to": new_state,
            "actor": "system",
            "actor_uid": None,
            "note": note,
            "at": now,
        }))
        count += 1

    return count


def _clear_expired_sessions() -> int:
    db = get_db()
    config = seed()
    cutoff = datetime.now(UTC) - timedelta(hours=config.settings.session_expiry_hours)
    count = 0

    expired = (
        db.collection("contacts")
        .where("session.startedAt", "<", cutoff)
        .limit(50)
        .get()
    )

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
```

- [ ] **Step 3: Implement routes.py — cron HTTP endpoints**

```python
# backend/src/support_service/jobs/routes.py
"""Cron endpoints. Called by Cloud Scheduler with OIDC tokens."""

from fastapi import APIRouter

from support_service.jobs.media_pass import run_media_pass
from support_service.jobs.sweep import run_sweep

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/media")
def media_job() -> dict:
    return run_media_pass()


@router.post("/sweep")
def sweep_job() -> dict:
    return run_sweep()
```

- [ ] **Step 4: Wire jobs router into main.py**

Add to `main.py`:
```python
from support_service.jobs.routes import router as jobs_router
app.include_router(jobs_router)
```

- [ ] **Step 5: Update jobs __init__**

```python
# backend/src/support_service/jobs/__init__.py
from support_service.jobs.routes import router as jobs_router

__all__ = ["jobs_router"]
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/support_service/jobs/ backend/src/support_service/main.py
git commit -m "feat: jobs module — 2-min media pass, hourly sweep"
```

---

### Task 7: Webhook orchestration — dedupe, route, respond

Wire the webhook stub from Task 2 into the full inbound message flow: dedupe → normalize → load contact → route → run step machine → send replies → persist.

**Files:**
- Modify: `backend/src/support_service/channel/webhook.py`
- Create: `backend/src/support_service/channel/handle.py`
- Test: `backend/tests/channel/test_handle.py`

**Interfaces:**
- Consumes: `normalize` from `channel/normalize.py`; `route` and all Decision types from `conversation/routing.py`; `begin`, `advance`, `Turn` from `conversation/steps.py`; `create_ticket` from `tickets`; `send_reply`, `send_text` from `channel/send.py`; `get_db`, `get_doc`, `set_doc`, `update_doc`, `to_firestore`, `from_firestore` from `firestore.py`; `ConfigSnapshot` from `config/models.py`; `seed` from `config/defaults.py`
- Produces: `handle_inbound(raw: dict) -> None`

- [ ] **Step 1: Implement handle.py — the orchestration layer**

```python
# backend/src/support_service/channel/handle.py
"""Inbound message orchestration: dedupe → normalize → route → step → reply → persist."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ulid import ULID

from support_service.channel.normalize import normalize
from support_service.channel.send import send_reply, send_text
from support_service.config.defaults import seed
from support_service.conversation.routing import (
    AppendToTicket,
    AskAboutRecentlyClosed,
    ContinueSession,
    Disambiguate,
    ReopenTicket,
    StartReport,
    route,
)
from support_service.conversation.steps import Row, SendButtons, SendList, SendText, advance, begin
from support_service.firestore import from_firestore, get_db, to_firestore
from support_service.models import (
    Contact,
    EventType,
    InboundMessage,
    Language,
    OpenTicket,
    TicketStatus,
)
from support_service.tickets.create import create_ticket


def handle_inbound(raw: dict[str, Any]) -> None:
    now = datetime.now(UTC)
    message = normalize(raw)
    db = get_db()

    if _is_duplicate(db, message.provider_message_id):
        return

    contact_data = _ensure_contact(db, message, now)
    contact = Contact(**from_firestore(contact_data))

    _append_message(db, message, now)
    _update_last_inbound(db, message.wa_number, now)

    open_tickets = _load_open_tickets(db, contact)
    outbound_map = _load_outbound_map(db, message.wa_number)
    closed_ids = frozenset(
        ref.ticket_id for ref in contact.recently_closed
    ) - frozenset(t.ticket_id for t in open_tickets)

    decision = route(
        contact,
        message,
        open_tickets,
        now=now,
        ticket_id_for_outbound=outbound_map,
        closed_ticket_ids=closed_ids,
    )

    config = seed()
    language = contact.language or Language.EN

    if isinstance(decision, StartReport):
        turn = begin(contact, config, now=now)
        _send_replies(message.wa_number, turn.replies, db, now)
        if turn.session:
            _update_session(db, message.wa_number, turn.session, now)
        if turn.learned_language:
            db.collection("contacts").document(message.wa_number).update({
                "language": turn.learned_language.value
            })

    elif isinstance(decision, ContinueSession):
        turn = advance(contact, message, config, now=now)
        _send_replies(message.wa_number, turn.replies, db, now)

        if turn.learned_language:
            db.collection("contacts").document(message.wa_number).update({
                "language": turn.learned_language.value
            })

        if turn.create:
            ticket_id = create_ticket(turn.create, message.wa_number, now=now)
            confirmation = config.text("ticket_created", Language(turn.create.language))
            confirmation = confirmation.format(ticket_id=ticket_id)
            _send_and_log(db, message.wa_number, confirmation, ticket_id, now)
            _stamp_ticket_on_messages(db, message.wa_number, ticket_id, now)
        elif turn.session:
            _update_session(db, message.wa_number, turn.session, now)

    elif isinstance(decision, AppendToTicket):
        _stamp_message(db, message, decision.ticket_id)
        _log_event(db, decision.ticket_id, EventType.MESSAGE_ADDED, now)
        text = config.text("appended", language).format(ticket_id=decision.ticket_id)
        _send_and_log(db, message.wa_number, text, decision.ticket_id, now)

    elif isinstance(decision, Disambiguate):
        rows = [
            Row(t.service_id, t.service_name) for t in decision.options
        ] + [Row("new", config.text("new_problem", language))]
        reply = SendList(config.text("ask_which_ticket", language), tuple(rows))
        _send_replies(message.wa_number, (reply,), db, now)

    elif isinstance(decision, AskAboutRecentlyClosed):
        service_name = decision.closed.service_id
        text = config.text("ask_recently_closed", language).format(
            service_name=service_name, ticket_id=decision.closed.ticket_id
        )
        buttons = (
            Row("reopen", config.text("yes_same", language)),
            Row("new", config.text("new_problem", language)),
        )
        reply = SendButtons(text, buttons)
        _send_replies(message.wa_number, (reply,), db, now)

    elif isinstance(decision, ReopenTicket):
        _reopen(db, decision.ticket_id, message.wa_number, now)
        text = config.text("reopened", language).format(ticket_id=decision.ticket_id)
        _send_and_log(db, message.wa_number, text, decision.ticket_id, now)


def _is_duplicate(db: Any, provider_message_id: str) -> bool:
    ref = db.collection("inbound").document(provider_message_id)
    if ref.get().exists:
        return True
    ref.set({"receivedAt": datetime.now(UTC)})
    return False


def _ensure_contact(db: Any, message: InboundMessage, now: datetime) -> dict:
    ref = db.collection("contacts").document(message.wa_number)
    doc = ref.get()
    if doc.exists:
        return doc.to_dict()
    data = to_firestore({
        "wa_number": message.wa_number,
        "display_name": None,
        "centre_name": None,
        "language": None,
        "session": None,
        "open_ticket_ids": [],
        "recently_closed": [],
        "last_inbound_at": now,
        "last_outbound_at": None,
        "created_at": now,
        "updated_at": now,
    })
    ref.set(data)
    return data


def _append_message(db: Any, message: InboundMessage, now: datetime) -> None:
    data = to_firestore({
        "message_id": message.provider_message_id,
        "direction": "in",
        "ticket_id": None,
        "type": message.type,
        "text": message.text,
        "created_at": now,
    })
    if message.attachment:
        data["attachment"] = to_firestore(message.attachment.model_dump())
    db.collection("contacts").document(message.wa_number).collection(
        "messages"
    ).document(message.provider_message_id).set(data)


def _update_last_inbound(db: Any, wa_number: str, now: datetime) -> None:
    db.collection("contacts").document(wa_number).update({
        "lastInboundAt": now, "updatedAt": now
    })


def _load_open_tickets(db: Any, contact: Contact) -> list[OpenTicket]:
    tickets = []
    for tid in contact.open_ticket_ids:
        doc = db.collection("tickets").document(tid).get()
        if doc.exists:
            data = doc.to_dict()
            tickets.append(OpenTicket(
                ticket_id=tid,
                service_id=data.get("serviceId", ""),
                service_name=data.get("serviceName", ""),
            ))
    return tickets


def _load_outbound_map(db: Any, wa_number: str) -> dict[str, str]:
    outbound = (
        db.collection("contacts").document(wa_number)
        .collection("messages")
        .where("direction", "==", "out")
        .where("ticketId", "!=", None)
        .order_by("createdAt", direction="DESCENDING")
        .limit(20)
        .get()
    )
    return {
        doc.to_dict().get("messageId", ""): doc.to_dict().get("ticketId", "")
        for doc in outbound
        if doc.to_dict().get("messageId")
    }


def _send_replies(wa_number: str, replies: tuple, db: Any, now: datetime) -> None:
    for reply in replies:
        message_id = send_reply(wa_number, reply)
        text = reply.body if hasattr(reply, "body") else None
        _log_outbound(db, wa_number, message_id, text, now)


def _send_and_log(
    db: Any, wa_number: str, text: str, ticket_id: str, now: datetime
) -> None:
    message_id = send_text(wa_number, text)
    _log_outbound(db, wa_number, message_id, text, now, ticket_id=ticket_id)


def _log_outbound(
    db: Any, wa_number: str, message_id: str, text: str | None, now: datetime, *,
    ticket_id: str | None = None
) -> None:
    ulid = str(ULID())
    db.collection("contacts").document(wa_number).collection("messages").document(ulid).set(
        to_firestore({
            "message_id": message_id or ulid,
            "direction": "out",
            "ticket_id": ticket_id,
            "type": "text",
            "text": text,
            "sent_via": "freeform",
            "provider_status": "queued",
            "created_at": now,
        })
    )
    db.collection("contacts").document(wa_number).update({
        "lastOutboundAt": now, "updatedAt": now
    })


def _update_session(db: Any, wa_number: str, session: Any, now: datetime) -> None:
    db.collection("contacts").document(wa_number).update(
        to_firestore({"session": session.model_dump(), "updated_at": now})
    )


def _stamp_message(db: Any, message: InboundMessage, ticket_id: str) -> None:
    db.collection("contacts").document(message.wa_number).collection(
        "messages"
    ).document(message.provider_message_id).update({"ticketId": ticket_id})


def _stamp_ticket_on_messages(
    db: Any, wa_number: str, ticket_id: str, now: datetime
) -> None:
    unstamped = (
        db.collection("contacts").document(wa_number)
        .collection("messages")
        .where("ticketId", "==", None)
        .get()
    )
    for doc in unstamped:
        doc.reference.update({"ticketId": ticket_id})


def _log_event(db: Any, ticket_id: str, event_type: EventType, now: datetime) -> None:
    db.collection("tickets").document(ticket_id).collection("events").document().set(
        to_firestore({
            "type": event_type,
            "from": None,
            "to": None,
            "actor": "bot",
            "actor_uid": None,
            "note": None,
            "at": now,
        })
    )


def _reopen(db: Any, ticket_id: str, wa_number: str, now: datetime) -> None:
    from google.cloud.firestore_v1 import transaction as fs_transaction

    @fs_transaction.transactional
    def _txn(txn: fs_transaction.Transaction) -> None:
        ticket_ref = db.collection("tickets").document(ticket_id)
        contact_ref = db.collection("contacts").document(wa_number)

        ticket_snap = ticket_ref.get(transaction=txn)
        contact_snap = contact_ref.get(transaction=txn)

        ticket_data = ticket_snap.to_dict() or {}
        contact_data = contact_snap.to_dict() or {}

        open_ids: list[str] = contact_data.get("openTicketIds", [])
        service_id = ticket_data.get("serviceId")
        for oid in open_ids:
            other = db.collection("tickets").document(oid).get(transaction=txn)
            if other.exists and other.to_dict().get("serviceId") == service_id:
                return

        txn.update(ticket_ref, to_firestore({
            "status": TicketStatus.OPEN,
            "sla_state": "ok",
            "closed_at": None,
            "updated_at": now,
        }))

        recently_closed = [
            rc for rc in contact_data.get("recentlyClosed", [])
            if rc.get("ticketId") != ticket_id
        ]
        txn.update(contact_ref, {
            "openTicketIds": open_ids + [ticket_id],
            "recentlyClosed": recently_closed,
            "updatedAt": now,
        })

        ticket_ref.collection("events").document().set(to_firestore({
            "type": EventType.STATUS_CHANGED,
            "from": TicketStatus.CLOSED,
            "to": TicketStatus.OPEN,
            "actor": "bot",
            "actor_uid": None,
            "note": "Reopened by contact",
            "at": now,
        }))

    _txn(db.transaction())
```

- [ ] **Step 2: Rewrite webhook.py to call handle_inbound**

```python
# backend/src/support_service/channel/webhook.py
"""Webhook endpoints — Gupshup delivers inbound messages and receipts here."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query, Request, Response

from support_service.channel.handle import handle_inbound
from support_service.firestore import get_db, to_firestore, update_doc
from support_service.models import EventType, ProviderStatus, TicketStatus

router = APIRouter(prefix="/webhook", tags=["webhook"])


def _check_secret(secret: str | None) -> bool:
    expected = os.environ.get("WEBHOOK_SECRET", "")
    if not expected:
        return True
    return secret == expected


@router.post("/gupshup")
def inbound(body: dict[str, Any], secret: str | None = Query(None)) -> Response:
    if not _check_secret(secret):
        return Response(status_code=401)

    msg_type = body.get("type")
    if msg_type != "message":
        return Response(status_code=200)

    handle_inbound(body)
    return Response(status_code=200)


@router.post("/gupshup/status")
def receipt(body: dict[str, Any], secret: str | None = Query(None)) -> Response:
    if not _check_secret(secret):
        return Response(status_code=401)

    if body.get("type") != "message-event":
        return Response(status_code=200)

    payload = body.get("payload", {})
    event_type = payload.get("type")
    gs_id = payload.get("gsId", "")

    status_map = {
        "enqueued": ProviderStatus.QUEUED,
        "sent": ProviderStatus.SENT,
        "delivered": ProviderStatus.DELIVERED,
        "read": ProviderStatus.READ,
        "failed": ProviderStatus.FAILED,
    }

    provider_status = status_map.get(event_type)
    if not provider_status or not gs_id:
        return Response(status_code=200)

    _update_message_status(gs_id, provider_status)

    if provider_status == ProviderStatus.DELIVERED:
        _try_close_on_delivery(gs_id)

    return Response(status_code=200)


def _update_message_status(gs_id: str, status: ProviderStatus) -> None:
    db = get_db()
    results = (
        db.collection_group("messages")
        .where("messageId", "==", gs_id)
        .limit(1)
        .get()
    )
    for doc in results:
        doc.reference.update({"providerStatus": status.value})


def _try_close_on_delivery(gs_id: str) -> None:
    db = get_db()
    now = datetime.now(UTC)

    results = (
        db.collection_group("messages")
        .where("messageId", "==", gs_id)
        .limit(1)
        .get()
    )
    if not results:
        return

    msg_data = results[0].to_dict()
    ticket_id = msg_data.get("ticketId")
    if not ticket_id:
        return

    ticket_ref = db.collection("tickets").document(ticket_id)
    ticket_snap = ticket_ref.get()
    if not ticket_snap.exists:
        return

    ticket_data = ticket_snap.to_dict()
    if ticket_data.get("status") != TicketStatus.RESOLVED:
        return

    wa_number = ticket_data.get("waNumber")

    ticket_ref.update(to_firestore({
        "status": TicketStatus.CLOSED,
        "closed_at": now,
        "updated_at": now,
        "resolution.delivery_state": ProviderStatus.DELIVERED,
    }))

    ticket_ref.collection("events").document().set(to_firestore({
        "type": EventType.DELIVERED,
        "from": TicketStatus.RESOLVED,
        "to": TicketStatus.CLOSED,
        "actor": "system",
        "actor_uid": None,
        "note": "Delivery receipt received",
        "at": now,
    }))

    if wa_number:
        contact_ref = db.collection("contacts").document(wa_number)
        contact_snap = contact_ref.get()
        if contact_snap.exists:
            contact_data = contact_snap.to_dict()
            open_ids = [oid for oid in contact_data.get("openTicketIds", []) if oid != ticket_id]
            recently_closed = contact_data.get("recentlyClosed", [])
            recently_closed.append({
                "ticketId": ticket_id,
                "serviceId": ticket_data.get("serviceId"),
                "closedAt": now,
            })
            contact_ref.update({
                "openTicketIds": open_ids,
                "recentlyClosed": recently_closed,
                "updatedAt": now,
            })
```

- [ ] **Step 3: Run all unit tests**

Run: `cd backend && uv run pytest -m "not firestore" -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/src/support_service/channel/
git commit -m "feat: wire webhook to full inbound flow — dedupe, route, respond"
```

---

### Task 8: Firestore seed script and composite indexes

Seed the services, config, copy, and settings documents. Define the composite indexes the queries need.

**Files:**
- Create: `backend/src/support_service/seed.py`
- Modify: `firestore.indexes.json`

**Interfaces:**
- Consumes: `seed()` from `config/defaults.py`; `set_doc`, `to_firestore` from `firestore.py`

- [ ] **Step 1: Implement seed.py**

```python
# backend/src/support_service/seed.py
"""Write seed data to Firestore. Run once at setup, idempotent."""

from support_service.config.defaults import COPY, SERVICES, seed
from support_service.firestore import get_db, to_firestore


def run_seed() -> None:
    db = get_db()

    for service in SERVICES:
        db.collection("services").document(service.id).set(
            to_firestore(service.model_dump())
        )

    for lang, strings in COPY.items():
        db.collection("config").document("copy").collection(lang.value).document("strings").set(
            strings
        )

    config = seed()
    db.collection("config").document("settings").set(
        to_firestore(config.settings.model_dump())
    )

    db.collection("config").document("languages").set({
        lang.value: True for lang in config.languages
    })

    print(f"Seeded {len(SERVICES)} services, {len(COPY)} language packs, settings")


if __name__ == "__main__":
    run_seed()
```

- [ ] **Step 2: Write composite indexes**

```json
{
  "indexes": [
    {
      "collectionGroup": "tickets",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "status", "order": "ASCENDING" },
        { "fieldPath": "createdAt", "order": "DESCENDING" }
      ]
    },
    {
      "collectionGroup": "tickets",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "serviceId", "order": "ASCENDING" },
        { "fieldPath": "status", "order": "ASCENDING" },
        { "fieldPath": "createdAt", "order": "DESCENDING" }
      ]
    },
    {
      "collectionGroup": "tickets",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "slaState", "order": "ASCENDING" },
        { "fieldPath": "createdAt", "order": "ASCENDING" }
      ]
    },
    {
      "collectionGroup": "tickets",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "status", "order": "ASCENDING" },
        { "fieldPath": "updatedAt", "order": "ASCENDING" }
      ]
    },
    {
      "collectionGroup": "messages",
      "queryScope": "COLLECTION_GROUP",
      "fields": [
        { "fieldPath": "ticketId", "order": "ASCENDING" },
        { "fieldPath": "createdAt", "order": "ASCENDING" }
      ]
    },
    {
      "collectionGroup": "messages",
      "queryScope": "COLLECTION_GROUP",
      "fields": [
        { "fieldPath": "attachment.state", "order": "ASCENDING" },
        { "fieldPath": "createdAt", "order": "ASCENDING" }
      ]
    },
    {
      "collectionGroup": "contacts",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "session.step", "order": "ASCENDING" },
        { "fieldPath": "session.lastActivityAt", "order": "ASCENDING" }
      ]
    }
  ],
  "fieldOverrides": []
}
```

- [ ] **Step 3: Add seed and indexes recipes to justfile**

Add:
```
seed:
    cd backend && uv run python -m support_service.seed
```

- [ ] **Step 4: Commit**

```bash
git add backend/src/support_service/seed.py firestore.indexes.json justfile
git commit -m "feat: Firestore seed script and composite indexes"
```

---

### Task 9: Dashboard — replace mocks with Firestore listeners and API writes

Replace `MOCK_TICKETS` with real Firestore `onSnapshot` listeners. Wire all write operations (status change, resolve, note, resend) through the REST API.

**Files:**
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/firestore.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/lib/types.ts` (minor — add `messages` and `events` as optional since they come from subcollections)

**Interfaces:**
- Consumes: Firebase JS SDK (`onSnapshot`, `collection`, `query`, `where`, `orderBy`); REST API endpoints from Task 4
- Produces: `useTickets()` hook, `api.changeStatus()`, `api.resolve()`, `api.addNote()`, `api.resend()`, `api.getAttachmentUrl()`

- [ ] **Step 1: Create api.ts — REST client**

```typescript
// frontend/src/lib/api.ts
import { auth } from "@/firebase"
import type { TicketStatus } from "./types"

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8088"

async function headers(): Promise<Record<string, string>> {
  const token = await auth?.currentUser?.getIdToken()
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

async function post(path: string, body?: object): Promise<Response> {
  return fetch(`${BASE}${path}`, {
    method: "POST",
    headers: await headers(),
    body: body ? JSON.stringify(body) : undefined,
  })
}

async function patch(path: string, body: object): Promise<Response> {
  return fetch(`${BASE}${path}`, {
    method: "PATCH",
    headers: await headers(),
    body: JSON.stringify(body),
  })
}

export const api = {
  changeStatus: (ticketId: string, to: TicketStatus, note?: string) =>
    patch(`/tickets/${ticketId}/status`, { to, note }),

  resolve: (ticketId: string, text: string) =>
    post(`/tickets/${ticketId}/resolution`, { text }),

  addNote: (ticketId: string, text: string) =>
    post(`/tickets/${ticketId}/notes`, { text }),

  resend: (ticketId: string) =>
    post(`/tickets/${ticketId}/resend`),

  getAttachmentUrl: async (messageId: string): Promise<string | null> => {
    const res = await fetch(`${BASE}/attachments/${messageId}/url`, {
      headers: await headers(),
    })
    if (!res.ok) return null
    const data = await res.json()
    return data.url ?? null
  },
}
```

- [ ] **Step 2: Create firestore.ts — live listeners**

```typescript
// frontend/src/lib/firestore.ts
import {
  collection,
  collectionGroup,
  onSnapshot,
  orderBy,
  query,
  where,
} from "firebase/firestore"
import type { Unsubscribe } from "firebase/firestore"
import { useEffect, useState } from "react"

import { db, isFirebaseConfigured } from "@/firebase"
import { MOCK_TICKETS } from "./mock"
import type { Message, Ticket, TicketEvent } from "./types"

export function useTickets(): { tickets: Ticket[]; loading: boolean } {
  const [tickets, setTickets] = useState<Ticket[]>(isFirebaseConfigured ? [] : MOCK_TICKETS)
  const [loading, setLoading] = useState(isFirebaseConfigured)

  useEffect(() => {
    if (!isFirebaseConfigured || !db) return

    const q = query(collection(db, "tickets"), orderBy("createdAt", "desc"))
    const unsub = onSnapshot(
      q,
      (snap) => {
        const docs = snap.docs.map((doc) => ({
          ticketId: doc.id,
          ...doc.data(),
          messages: [],
          events: [],
        })) as Ticket[]
        setTickets(docs)
        setLoading(false)
      },
      (err) => {
        console.error("tickets listener error:", err)
        setLoading(false)
      },
    )
    return unsub
  }, [])

  return { tickets, loading }
}

export function useTicketDetail(ticketId: string | null): {
  messages: Message[]
  events: TicketEvent[]
} {
  const [messages, setMessages] = useState<Message[]>([])
  const [events, setEvents] = useState<TicketEvent[]>([])

  useEffect(() => {
    if (!ticketId || !isFirebaseConfigured || !db) {
      setMessages([])
      setEvents([])
      return
    }

    const unsubs: Unsubscribe[] = []

    // Messages are under contacts/{waNumber}/messages, filtered by ticketId.
    // Use a collection group query.
    const msgQ = query(
      collectionGroup(db, "messages"),
      where("ticketId", "==", ticketId),
      orderBy("createdAt", "asc"),
    )
    unsubs.push(
      onSnapshot(msgQ, (snap) => {
        setMessages(snap.docs.map((d) => ({ messageId: d.id, ...d.data() }) as Message))
      }),
    )

    // Events are under tickets/{ticketId}/events
    const evtQ = query(
      collection(db, "tickets", ticketId, "events"),
      orderBy("at", "asc"),
    )
    unsubs.push(
      onSnapshot(evtQ, (snap) => {
        setEvents(snap.docs.map((d) => ({ eventId: d.id, ...d.data() }) as TicketEvent))
      }),
    )

    return () => unsubs.forEach((u) => u())
  }, [ticketId])

  return { messages, events }
}
```

- [ ] **Step 3: Update App.tsx — swap mock data for hooks and API calls**

Replace the mock-driven `useState` and callbacks with:
- `const { tickets, loading: ticketsLoading } = useTickets()`
- `const { messages, events } = useTicketDetail(openId)`
- `changeStatus` → `api.changeStatus(id, to).then(...)` — optimistic update kept for snappy UI, rolled back on API error
- `dispatch` (resolve) → `api.resolve(id, text)`
- `handleNote` → `api.addNote(id, text)` with a text input instead of hardcoded string
- `handleResend` → `api.resend(id)`

Keep the mock path: when `!isFirebaseConfigured`, the existing mock-driven code runs unchanged. The conditional is already there via the `demo` flag in auth.

- [ ] **Step 4: Add VITE_API_URL to .env.example**

```
VITE_API_URL=http://localhost:8088
```

- [ ] **Step 5: Run frontend type check and tests**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.app.json && pnpm test`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/firestore.ts frontend/src/App.tsx frontend/src/lib/types.ts frontend/.env.example
git commit -m "feat: wire dashboard to Firestore listeners and REST API"
```

---

### Task 10: Final integration — CORS, receipt handling for mediaId, lint pass

Tie up loose ends: add CORS middleware so the dashboard can talk to the API, ensure the Gupshup `mediaId` is persisted on inbound media messages for the cron to use, and run a full lint+type check.

**Files:**
- Modify: `backend/src/support_service/main.py`
- Modify: `backend/src/support_service/channel/handle.py`

**Interfaces:**
- Consumes: FastAPI CORSMiddleware
- Produces: complete, lint-clean, type-checked codebase

- [ ] **Step 1: Add CORS middleware to main.py**

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://ai-powered-479515.web.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 2: Persist mediaId on inbound media messages**

In `handle.py`'s `_append_message`, when the message has an attachment, include the Gupshup `mediaId` from the raw payload so the cron can fetch it later. The raw payload's `payload.payload.mediaId` needs to be carried through the normalize step. Add a `media_id: str | None` field to the `Attachment` model in `models.py`.

- [ ] **Step 3: Run full lint and type check**

Run: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run pyright`
Fix any issues found.

- [ ] **Step 4: Run the complete test suite**

Run: `cd backend && uv run pytest -m "not firestore" -v`
Expected: All pass

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: CORS, mediaId persistence, lint clean"
```
