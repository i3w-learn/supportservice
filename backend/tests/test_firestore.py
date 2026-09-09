from support_service.firestore import from_firestore, to_firestore


def test_to_firestore_converts_snake_to_camel() -> None:
    assert to_firestore({"open_ticket_ids": ["TKT-1"], "wa_number": "91123"}) == {
        "openTicketIds": ["TKT-1"],
        "waNumber": "91123",
    }


def test_from_firestore_converts_camel_to_snake() -> None:
    assert from_firestore({"openTicketIds": ["TKT-1"], "waNumber": "91123"}) == {
        "open_ticket_ids": ["TKT-1"],
        "wa_number": "91123",
    }


def test_nested_dicts_are_converted() -> None:
    assert to_firestore({"session": {"last_activity_at": 123}}) == {
        "session": {"lastActivityAt": 123},
    }
