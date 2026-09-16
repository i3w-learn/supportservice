from unittest.mock import patch

from support_service.conversation.steps import Row, SendList, SendTemplate, SendText
from support_service.models import Language


@patch("support_service.services.channel_service._send", return_value="msg-001")
def test_send_text_dispatches(mock_send: object) -> None:
    from support_service.services.channel_service import send_reply

    assert send_reply("919876543210", SendText("Hello")) == "msg-001"


@patch("support_service.services.channel_service._send", return_value="msg-002")
def test_send_list_dispatches(mock_send: object) -> None:
    from support_service.services.channel_service import send_reply

    rows = (Row("mr", "मराठी"), Row("bn", "বাংলা"))
    assert send_reply("919876543210", SendList("Pick one", rows)) == "msg-002"


@patch("support_service.services.channel_service._send", return_value="msg-003")
def test_send_template_dispatches_with_its_language_and_params(mock_send) -> None:
    from support_service.services.channel_service import send_reply

    reply = SendTemplate("ticket_created_confirmation", Language.HI, ("TKT-1", "डिवाइस", "+91"))

    assert send_reply("919876543210", reply) == "msg-003"

    _, message = mock_send.call_args.args
    assert message["template"]["name"] == "ticket_created_confirmation"
    assert message["template"]["language"]["code"] == "hi"
    assert [p["text"] for p in message["template"]["components"][0]["parameters"]] == [
        "TKT-1",
        "डिवाइस",
        "+91",
    ]
