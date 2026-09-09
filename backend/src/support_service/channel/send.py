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
