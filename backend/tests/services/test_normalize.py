from support_service.models import AttachmentState, MessageType
from support_service.services.channel_service import normalize


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
                "url": "https://filemanager.gupshup.io/fm/wamedia/TestApp/img-1",
                "contentType": "image/png",
                "urlExpiry": 1726492800000,
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
    assert msg.attachment.mime_type == "image/png"
    assert msg.attachment.media_url == "https://filemanager.gupshup.io/fm/wamedia/TestApp/img-1"


def test_video_without_content_type_falls_back_to_a_guess() -> None:
    payload = {
        "app": "TestApp",
        "timestamp": 1725888000000,
        "version": 2,
        "type": "message",
        "payload": {
            "id": "wamid.VID1",
            "source": "919876543210",
            "type": "video",
            "payload": {"url": "https://filemanager.gupshup.io/fm/wamedia/TestApp/vid-1"},
            "sender": {"phone": "919876543210", "name": "Test"},
        },
    }
    msg = normalize(payload)
    assert msg.type == MessageType.VIDEO
    assert msg.attachment is not None
    assert msg.attachment.mime_type == "video/mp4"
    assert msg.attachment.media_url == "https://filemanager.gupshup.io/fm/wamedia/TestApp/vid-1"


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


def test_the_whatsapp_profile_name_is_captured() -> None:
    """The flow never asks for a name, so this is the only one we get."""
    payload = {
        "app": "TestApp",
        "timestamp": 1725888000000,
        "version": 2,
        "type": "message",
        "payload": {
            "id": "wamid.ABC128",
            "source": "919876543210",
            "type": "text",
            "payload": {"text": "Hi"},
            "sender": {"phone": "919876543210", "name": "Sunita Devi"},
        },
    }

    assert normalize(payload).sender_name == "Sunita Devi"


def test_template_quick_reply_carries_the_button_text() -> None:
    """A tap on a template's quick-reply button arrives as `quick_reply` with
    the label under `text`, not `title` — unlike our own interactive buttons."""
    payload = {
        "app": "TestApp",
        "timestamp": 1725888000000,
        "version": 2,
        "type": "message",
        "payload": {
            "id": "wamid.ABC126",
            "source": "919876543210",
            "type": "quick_reply",
            "payload": {"text": "Device", "type": "button"},
            "sender": {"phone": "919876543210", "name": "Test"},
            "context": {"id": "wamid.PREV", "gsId": "gs-1"},
        },
    }
    msg = normalize(payload)
    assert msg.type == MessageType.INTERACTIVE
    assert msg.text == "Device"
    assert msg.reply_id is None
    assert msg.context_message_id == "wamid.PREV"
