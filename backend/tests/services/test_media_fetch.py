"""fetch_attachment — unit, no emulator, no network (httpx and storage are faked)."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from support_service.services import media_service as media_module
from support_service.services.media_service import (
    MAX_ATTEMPTS,
    MediaNotReady,
    fetch_attachment,
    requeue_attachment,
)

WA = "919876500001"
MSG = "wamid.abc"
URL = "https://filemanager.gupshup.io/fm/wamedia/TestApp/abc"


@pytest.fixture
def ref(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    db = MagicMock()
    monkeypatch.setattr(media_module, "get_db", lambda: db)
    messages = db.collection.return_value.document.return_value.collection.return_value
    return messages.document.return_value


@pytest.fixture
def bucket(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake_storage = MagicMock()
    monkeypatch.setattr(media_module, "storage", fake_storage)
    return fake_storage.bucket.return_value


def _attachment(ref: MagicMock, **fields: object) -> None:
    ref.get.return_value.exists = True
    ref.get.return_value.to_dict.return_value = {
        "attachment": {
            "state": "pending",
            "mimeType": "image/jpeg",
            "attempts": 0,
            "mediaUrl": URL,
            **fields,
        }
    }


def _gupshup_returns(
    monkeypatch: pytest.MonkeyPatch, status: int, content: bytes = b""
) -> MagicMock:
    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        return httpx.Response(status, content=content, request=httpx.Request("GET", url))

    spy = MagicMock(side_effect=fake_get)
    monkeypatch.setattr(httpx, "get", spy)
    return spy


def test_downloads_into_the_bucket_and_marks_stored(
    ref: MagicMock, bucket: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _attachment(ref)
    _gupshup_returns(monkeypatch, 200, b"jpeg")

    assert fetch_attachment(WA, MSG) == "stored"

    path = f"attachments/{WA}/{MSG}"
    bucket.blob.assert_called_once_with(path)
    bucket.blob.return_value.upload_from_string.assert_called_once_with(
        b"jpeg", content_type="image/jpeg"
    )
    updates = ref.update.call_args.args[0]
    assert updates["attachment.state"] == "stored"
    assert updates["attachment.storagePath"] == path
    assert updates["attachment.sizeBytes"] == 4


def test_already_stored_is_not_downloaded_again(
    ref: MagicMock, bucket: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _attachment(ref, state="stored")
    spy = _gupshup_returns(monkeypatch, 200)

    assert fetch_attachment(WA, MSG) == "stored"

    spy.assert_not_called()
    ref.update.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        None,
        "http://filemanager.gupshup.io/fm/x",
        "https://evil.example/x",
        "https://gupshup.io.evil.example/x",
        "https://evilgupshup.io/x",
    ],
)
def test_refuses_anything_but_a_gupshup_https_url(
    url: str | None, ref: MagicMock, bucket: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _attachment(ref, mediaUrl=url)
    spy = _gupshup_returns(monkeypatch, 200)

    assert fetch_attachment(WA, MSG) == "failed"

    spy.assert_not_called()
    ref.update.assert_called_once_with({"attachment.state": "failed"})


def test_failed_download_raises_so_the_task_retries(
    ref: MagicMock, bucket: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _attachment(ref, attempts=0)
    _gupshup_returns(monkeypatch, 502)

    with pytest.raises(MediaNotReady):
        fetch_attachment(WA, MSG)

    ref.update.assert_called_once_with({"attachment.attempts": 1})
    bucket.blob.assert_not_called()


def test_gives_up_after_max_attempts(
    ref: MagicMock, bucket: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _attachment(ref, attempts=MAX_ATTEMPTS - 1)
    _gupshup_returns(monkeypatch, 502)

    assert fetch_attachment(WA, MSG) == "failed"

    ref.update.assert_called_once_with(
        {"attachment.state": "failed", "attachment.attempts": MAX_ATTEMPTS}
    )


# --- requeue_attachment: the dashboard's Retry button -----------------------


@pytest.fixture
def group_query(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    db = MagicMock()
    monkeypatch.setattr(media_module, "get_db", lambda: db)
    return db.collection_group.return_value.where.return_value.limit.return_value


def _found(query: MagicMock, state: str) -> MagicMock:
    doc = MagicMock()
    doc.id = MSG
    doc.reference.parent.parent.id = WA
    doc.to_dict.return_value = {"attachment": {"state": state, "attempts": MAX_ATTEMPTS}}
    query.get.return_value = [doc]
    return doc


@pytest.mark.parametrize("state", ["failed", "pending"])
def test_failed_or_stuck_download_is_queued_again(
    group_query: MagicMock, enqueued: MagicMock, state: str
) -> None:
    doc = _found(group_query, state)

    assert requeue_attachment(MSG) is True

    doc.reference.update.assert_called_once_with(
        {"attachment.state": "pending", "attachment.attempts": 0}
    )
    enqueued.assert_called_once_with("/tasks/media", {"wa_number": WA, "message_id": MSG})


def test_saved_file_is_not_queued_again(group_query: MagicMock, enqueued: MagicMock) -> None:
    doc = _found(group_query, "stored")

    assert requeue_attachment(MSG) is False

    doc.reference.update.assert_not_called()
    enqueued.assert_not_called()


def test_unknown_message_is_not_queued(group_query: MagicMock, enqueued: MagicMock) -> None:
    group_query.get.return_value = []

    assert requeue_attachment(MSG) is False
    enqueued.assert_not_called()
