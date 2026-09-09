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
