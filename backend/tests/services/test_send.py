import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

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


# --- templates -------------------------------------------------------------
#
# Gupshup has a separate endpoint for templates and wants the template's
# Gupshup id, not its name. Each language variant has its own id.


@pytest.fixture
def fresh_cache(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[str, str], str]:
    from support_service.services import channel_service

    cache: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(channel_service, "_template_ids", cache)
    monkeypatch.setattr(channel_service, "_template_ids_loaded_at", None)
    return cache


def _warm(monkeypatch: pytest.MonkeyPatch, cache: dict[tuple[str, str], str], **ids: str) -> None:
    """Fill the cache as if it were just loaded, so no lookup hits the network."""
    from support_service.services import channel_service

    for key, template_id in ids.items():
        name, code = key.rsplit("__", 1)
        cache[(name, code)] = template_id
    monkeypatch.setattr(channel_service, "_template_ids_loaded_at", datetime.now(UTC))


@patch("support_service.services.channel_service._post", return_value="msg-003")
def test_send_template_posts_id_and_params_to_template_endpoint(
    mock_post, monkeypatch: pytest.MonkeyPatch, fresh_cache
) -> None:
    from support_service.services import channel_service
    from support_service.services.channel_service import send_reply

    _warm(monkeypatch, fresh_cache, ticket_created_confirmation__hi="uuid-hi")
    reply = SendTemplate("ticket_created_confirmation", Language.HI, ("TKT-1", "डिवाइस", "+91"))

    assert send_reply("919876543210", reply) == "msg-003"

    url, destination, body = mock_post.call_args.args
    assert url == channel_service.TEMPLATE_URL
    assert destination == "919876543210"
    assert json.loads(body["template"]) == {"id": "uuid-hi", "params": ["TKT-1", "डिवाइस", "+91"]}
    assert "message" not in body


def test_template_id_prefers_the_requested_language(monkeypatch, fresh_cache) -> None:
    from support_service.services.channel_service import _template_id

    _warm(monkeypatch, fresh_cache, ticket_resolved__en="uuid-en", ticket_resolved__hi="uuid-hi")

    assert _template_id("ticket_resolved", "hi") == "uuid-hi"


def test_template_id_falls_back_to_english_when_language_not_approved(
    monkeypatch, fresh_cache
) -> None:
    from support_service.services.channel_service import _template_id

    _warm(monkeypatch, fresh_cache, ticket_resolved__en="uuid-en")

    assert _template_id("ticket_resolved", "mr") == "uuid-en"


def test_template_id_raises_when_nothing_is_approved(monkeypatch, fresh_cache) -> None:
    from support_service.services.channel_service import _template_id

    _warm(monkeypatch, fresh_cache, other_template__en="uuid-other")

    with pytest.raises(LookupError, match="ticket_resolved"):
        _template_id("ticket_resolved", "hi")


def test_template_id_loads_the_cache_when_empty(monkeypatch, fresh_cache) -> None:
    from support_service.services import channel_service

    def fake_load() -> None:
        fresh_cache[("ticket_resolved", "en")] = "uuid-en"
        channel_service._template_ids_loaded_at = datetime.now(UTC)

    monkeypatch.setattr(channel_service, "_load_template_ids", fake_load)

    assert channel_service._template_id("ticket_resolved", "en") == "uuid-en"


def test_load_template_ids_keeps_approved_only_and_normalises_language(
    monkeypatch, fresh_cache
) -> None:
    from support_service.services import channel_service

    monkeypatch.setenv("GUPSHUP_API_KEY", "k")
    monkeypatch.setenv("GUPSHUP_APP_NAME", "TestApp")
    monkeypatch.setenv("GUPSHUP_SOURCE_NUMBER", "91910000000")

    listing = {
        "status": "success",
        "templates": [
            {
                "elementName": "ticket_resolved",
                "languageCode": "en_US",
                "status": "APPROVED",
                "id": "a",
            },
            {
                "elementName": "ticket_resolved",
                "languageCode": "hi",
                "status": "REJECTED",
                "id": "b",
            },
            {
                "elementName": "ticket_resolved",
                "languageCode": "mr",
                "status": "APPROVED",
                "id": "c",
            },
            {"elementName": "old_promo", "languageCode": "en", "status": "ARCHIVED", "id": "d"},
        ],
    }
    response = MagicMock()
    response.json.return_value = listing
    get = MagicMock(return_value=response)
    monkeypatch.setattr(channel_service.httpx, "get", get)

    channel_service._load_template_ids()

    assert fresh_cache == {("ticket_resolved", "en"): "a", ("ticket_resolved", "mr"): "c"}
    assert get.call_args.args[0] == channel_service.TEMPLATE_LIST_URL.format(app_name="TestApp")
    assert get.call_args.kwargs["headers"] == {"apikey": "k"}
