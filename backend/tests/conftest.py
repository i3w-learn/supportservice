"""Test setup.

Two kinds of test in this suite:

  unit         Pure functions over data — the step machine (§7), the routing
               table (§6), transition validation (§8), payload normalization.
               No Firestore, no network, no emulator. Milliseconds.

  firestore    Transactions, invariants, index-backed queries. Needs the
               local emulator. Mark these with @pytest.mark.firestore.

The guard below only applies to the second kind. Without it, firebase-admin
would silently talk to the real project and the suite would write into
production Firestore.
"""

import os
from unittest.mock import MagicMock

import pytest

from support_service.services import task_service

REQUIRED_EMULATOR_VARS = (
    "FIRESTORE_EMULATOR_HOST",
    "FIREBASE_AUTH_EMULATOR_HOST",
)


def _missing_emulator_vars() -> list[str]:
    return [var for var in REQUIRED_EMULATOR_VARS if not os.environ.get(var)]


@pytest.fixture(autouse=True)
def guard_against_real_firestore(request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("firestore") is None:
        return

    missing = _missing_emulator_vars()
    if missing:
        pytest.skip(
            f"{', '.join(missing)} not set. Start the emulator with "
            "`just emulators`, then run `just test`."
        )


@pytest.fixture(autouse=True)
def enqueued(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Records Cloud Tasks instead of creating them, so no test reaches GCP."""
    recorder = MagicMock()
    monkeypatch.setattr(task_service, "enqueue", recorder)
    return recorder
