"""check_sla — unit, no emulator. Runs as a delayed Cloud Task per deadline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from support_service.config.defaults import seed
from support_service.services import ticket_service as ticket_module
from support_service.services.ticket_service import check_sla

SETTINGS = seed().settings
NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
PAST_REMINDER = timedelta(hours=SETTINGS.sla_reminder_hours, minutes=1)
PAST_BREACH = timedelta(hours=SETTINGS.sla_breach_hours, minutes=1)


@pytest.fixture
def ticket_ref(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    db = MagicMock()
    monkeypatch.setattr(ticket_module, "get_db", lambda: db)
    return db.collection.return_value.document.return_value


def _ticket(ref: MagicMock, *, age: timedelta, **fields: object) -> None:
    ref.get.return_value.exists = True
    ref.get.return_value.to_dict.return_value = {
        "status": "open",
        "slaState": "ok",
        "createdAt": NOW - age,
        **fields,
    }


def test_past_breach_is_flagged_breached(ticket_ref: MagicMock) -> None:
    _ticket(ticket_ref, age=PAST_BREACH)

    assert check_sla("TKT-1", now=NOW) == "breached"

    assert ticket_ref.update.call_args.args[0]["slaState"] == "breached"
    event = ticket_ref.collection.return_value.document.return_value.set.call_args.args[0]
    assert event["type"] == "sla_flagged"
    assert (event["from"], event["to"]) == ("ok", "breached")


def test_past_reminder_is_flagged_reminder_due(ticket_ref: MagicMock) -> None:
    _ticket(ticket_ref, age=PAST_REMINDER)

    assert check_sla("TKT-1", now=NOW) == "reminder_due"


def test_reminder_due_escalates_at_the_breach_deadline(ticket_ref: MagicMock) -> None:
    _ticket(ticket_ref, age=PAST_BREACH, slaState="reminder_due")

    assert check_sla("TKT-1", now=NOW) == "breached"


def test_already_reminder_due_is_not_reflagged(ticket_ref: MagicMock) -> None:
    _ticket(ticket_ref, age=PAST_REMINDER, slaState="reminder_due")

    assert check_sla("TKT-1", now=NOW) is None
    ticket_ref.update.assert_not_called()


def test_inside_the_window_is_untouched(ticket_ref: MagicMock) -> None:
    _ticket(ticket_ref, age=timedelta(hours=1))

    assert check_sla("TKT-1", now=NOW) is None
    ticket_ref.update.assert_not_called()


@pytest.mark.parametrize("status", ["resolved", "closed"])
def test_answered_ticket_is_untouched(ticket_ref: MagicMock, status: str) -> None:
    _ticket(ticket_ref, age=PAST_BREACH, status=status)

    assert check_sla("TKT-1", now=NOW) is None
    ticket_ref.update.assert_not_called()


def test_deleted_ticket_is_ignored(ticket_ref: MagicMock) -> None:
    ticket_ref.get.return_value.exists = False

    assert check_sla("TKT-1", now=NOW) is None


def test_reopened_ticket_is_measured_from_the_reopen(ticket_ref: MagicMock) -> None:
    _ticket(ticket_ref, age=PAST_BREACH * 3, slaStartedAt=NOW - timedelta(hours=1))

    assert check_sla("TKT-1", now=NOW) is None
    ticket_ref.update.assert_not_called()


def test_reopened_ticket_gets_its_own_reminder(ticket_ref: MagicMock) -> None:
    _ticket(ticket_ref, age=PAST_BREACH * 3, slaStartedAt=NOW - PAST_REMINDER)

    assert check_sla("TKT-1", now=NOW) == "reminder_due"
