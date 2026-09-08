"""Firestore — proves the emulator wiring works through firebase-admin.

This is the canary. It goes through the same SDK the service uses (§10), not
`google.cloud.firestore` directly, so a failure here means the setup is wrong
rather than the business logic.

Skipped when the emulator env vars are absent, so `just test-unit` stays
offline. `just test` sets them, so it must pass there.
"""

import firebase_admin
import pytest
from firebase_admin import firestore

PROJECT_ID = "ai-powered-479515"


@pytest.mark.firestore
def test_write_then_read_round_trips() -> None:
    app = firebase_admin.initialize_app(options={"projectId": PROJECT_ID}, name="wiring")
    try:
        doc = firestore.client(app).collection("_wiring_check").document("canary")

        doc.set({"seq": 1})
        assert doc.get().to_dict() == {"seq": 1}

        doc.delete()
        assert not doc.get().exists
    finally:
        firebase_admin.delete_app(app)
