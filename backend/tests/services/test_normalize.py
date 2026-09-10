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
    assert msg.attachment.media_id == "76534618"


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
