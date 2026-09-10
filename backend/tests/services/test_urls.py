"""Unit — no emulator, no network.

Firestore (`get_db`) and Cloud Storage (`storage`) are monkeypatched at the
point `urls.py` imports them, same convention as admin_api/test_routes.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from support_service.services import media_service as urls_module
from support_service.services.media_service import get_signed_url

MESSAGE_ID = "gs-msg-1"


def _doc(data: dict[str, object]) -> MagicMock:
    doc = MagicMock()
    doc.to_dict.return_value = data
    return doc


@pytest.fixture
def mock_db(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    db = MagicMock()
    monkeypatch.setattr(urls_module, "get_db", lambda: db)
    return db


def _query(mock_db: MagicMock) -> MagicMock:
    return mock_db.collection_group.return_value.where.return_value.limit.return_value


def test_no_matching_message_returns_none(mock_db: MagicMock) -> None:
    _query(mock_db).get.return_value = []

    assert get_signed_url(MESSAGE_ID) is None


def test_attachment_not_stored_returns_none(mock_db: MagicMock) -> None:
    _query(mock_db).get.return_value = [_doc({"attachment": {"state": "pending"}})]

    assert get_signed_url(MESSAGE_ID) is None


def test_missing_storage_path_returns_none(mock_db: MagicMock) -> None:
    _query(mock_db).get.return_value = [_doc({"attachment": {"state": "stored"}})]

    assert get_signed_url(MESSAGE_ID) is None


def test_stored_attachment_returns_signed_url(
    mock_db: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _query(mock_db).get.return_value = [
        _doc(
            {
                "attachment": {
                    "state": "stored",
                    "storagePath": "attachments/919876500001/wamid.abc",
                }
            }
        )
    ]

    mock_bucket = MagicMock()
    mock_blob = mock_bucket.blob.return_value
    mock_blob.generate_signed_url.return_value = "https://storage.example/signed"
    mock_storage = MagicMock()
    mock_storage.bucket.return_value = mock_bucket
    monkeypatch.setattr(urls_module, "storage", mock_storage)

    url = get_signed_url(MESSAGE_ID)

    assert url == "https://storage.example/signed"
    mock_bucket.blob.assert_called_once_with("attachments/919876500001/wamid.abc")
    mock_blob.generate_signed_url.assert_called_once()


def test_query_filters_by_message_id(mock_db: MagicMock) -> None:
    _query(mock_db).get.return_value = []

    get_signed_url(MESSAGE_ID)

    mock_db.collection_group.assert_called_once_with("messages")
    mock_db.collection_group.return_value.where.assert_called_once_with(
        "messageId", "==", MESSAGE_ID
    )
