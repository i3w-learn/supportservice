"""The QR greeting carries the centre id; nothing else in it is trusted."""

from __future__ import annotations

import pytest

from support_service.conversation.centres import parse_centre_id


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hi, I need support. Centre ID: NGP-AWC-017", "NGP-AWC-017"),
        ("centre id ngp-awc-17", "NGP-AWC-017"),
        ("Center Id - NGP-AWC-0066 please help", "NGP-AWC-066"),
        ("नमस्कार Centre ID: NGP-AWC-001", "NGP-AWC-001"),
    ],
)
def test_reads_the_centre_id_out_of_a_qr_greeting(text: str, expected: str) -> None:
    assert parse_centre_id(text) == expected


@pytest.mark.parametrize("text", [None, "", "Hi", "My headset broke", "NGP-AWC-017"])
def test_a_plain_message_has_no_centre(text: str | None) -> None:
    assert parse_centre_id(text) is None
