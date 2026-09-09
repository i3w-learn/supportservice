"""channel — see §3 of support-system-design.md."""

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
