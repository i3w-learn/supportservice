"""Report flow step machine (§7). Unit tests — no emulator, no network."""

from datetime import UTC, datetime

import pytest

from support_service.config.defaults import seed
from support_service.conversation.steps import (
    SendButtons,
    SendList,
    SendText,
    advance,
    begin,
    finish_idle,
)
from support_service.models import (
    Attachment,
    Contact,
    Flow,
    InboundMessage,
    Language,
    MessageType,
    Session,
    Step,
)

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
CONFIG = seed()


def tap(row_id: str) -> InboundMessage:
    return InboundMessage(
        provider_message_id="wamid.x",
        wa_number="918827450192",
        type=MessageType.INTERACTIVE,
        reply_id=row_id,
        received_at=NOW,
    )


def say(body: str) -> InboundMessage:
    return InboundMessage(
        provider_message_id="wamid.x",
        wa_number="918827450192",
        type=MessageType.TEXT,
        text=body,
        received_at=NOW,
    )


def photo() -> InboundMessage:
    return InboundMessage(
        provider_message_id="wamid.x",
        wa_number="918827450192",
        type=MessageType.IMAGE,
        attachment=Attachment(),
        received_at=NOW,
    )


def at(step: Step, **draft: str) -> Contact:
    return Contact(
        wa_number="918827450192",
        language=Language(draft["language"]) if "language" in draft else None,
        session=Session(
            flow=Flow.REPORT, step=step, draft=draft, started_at=NOW, last_activity_at=NOW
        ),
    )


class TestOpening:
    def test_new_contact_is_asked_for_language(self) -> None:
        turn = begin(Contact(wa_number="918827450192"), CONFIG, now=NOW)
        assert isinstance(turn.replies[0], SendList)
        assert turn.session is not None
        assert turn.session.step is Step.LANGUAGE

    def test_known_language_skips_straight_to_product(self) -> None:
        contact = Contact(wa_number="918827450192", language=Language.HI)
        turn = begin(contact, CONFIG, now=NOW)
        assert turn.session is not None
        assert turn.session.step is Step.SERVICE
        assert isinstance(turn.replies[0], SendList)


class TestHappyPath:
    def test_full_walk_reaches_a_draft(self) -> None:
        contact = Contact(wa_number="918827450192")

        turn = begin(contact, CONFIG, now=NOW)
        contact = contact.model_copy(update={"session": turn.session})

        for message, expected in [
            (tap("hi"), Step.SERVICE),
            (tap("anganwadi-vr"), Step.NAME),
            (say("सुनीता देवी"), Step.CENTRE),
            (say("AWC 42, Kolar Road"), Step.CATEGORY),
            (tap("headset"), Step.DESCRIPTION),
        ]:
            turn = advance(contact, message, CONFIG, now=NOW)
            assert turn.session is not None
            assert turn.session.step is expected
            contact = contact.model_copy(update={"session": turn.session})

        turn = advance(contact, say("charge karne par bhi nahi chalta"), CONFIG, now=NOW)
        contact = contact.model_copy(update={"session": turn.session})
        turn = advance(contact, tap("done"), CONFIG, now=NOW)

        assert turn.session is None, "the session must be cleared on completion"
        assert turn.create is not None
        assert turn.create.language is Language.HI
        assert turn.create.service_id == "anganwadi-vr"
        assert turn.create.category_id == "headset"
        assert turn.create.display_name == "सुनीता देवी"
        assert turn.create.description == "charge karne par bhi nahi chalta"

    def test_language_choice_is_learned(self) -> None:
        turn = advance(at(Step.LANGUAGE), tap("ta"), CONFIG, now=NOW)
        assert turn.learned_language is Language.TA


class TestReturningContacts:
    def test_known_name_and_centre_skip_two_steps(self) -> None:
        """A second ticket is 3 taps, not 6 (§7)."""
        contact = Contact(
            wa_number="918827450192",
            language=Language.HI,
            display_name="सुनीता देवी",
            centre_name="AWC 42",
            session=Session(
                flow=Flow.REPORT, step=Step.SERVICE, started_at=NOW, last_activity_at=NOW
            ),
        )
        turn = advance(contact, tap("poshan-ai"), CONFIG, now=NOW)
        assert turn.session is not None
        assert turn.session.step is Step.CATEGORY, "name and centre must be skipped"
        assert turn.session.draft["display_name"] == "सुनीता देवी"


class TestInvalidInput:
    def test_unknown_row_re_asks_without_advancing(self) -> None:
        turn = advance(at(Step.SERVICE, language="en"), tap("not-a-product"), CONFIG, now=NOW)
        assert turn.session is not None
        assert turn.session.step is Step.SERVICE
        assert isinstance(turn.replies[0], SendText), "a nudge comes before the re-ask"
        assert isinstance(turn.replies[1], SendList)

    def test_a_digit_works_when_list_rendering_fails(self) -> None:
        """Cheap handsets sometimes cannot render interactive lists."""
        turn = advance(at(Step.SERVICE, language="en"), say("2"), CONFIG, now=NOW)
        assert turn.session is not None
        assert turn.session.draft["service_id"] == "poshan-ai"

    def test_digit_out_of_range_is_rejected(self) -> None:
        turn = advance(at(Step.SERVICE, language="en"), say("99"), CONFIG, now=NOW)
        assert turn.session is not None
        assert turn.session.step is Step.SERVICE

    @pytest.mark.parametrize("name", ["", "   ", "x" * 81])
    def test_name_length_is_enforced(self, name: str) -> None:
        turn = advance(at(Step.NAME, language="en"), say(name), CONFIG, now=NOW)
        assert turn.session is not None
        assert turn.session.step is Step.NAME

    def test_category_must_belong_to_the_chosen_product(self) -> None:
        """`audio` is a German AI category — it must not be accepted for Poshan AI."""
        contact = at(Step.CATEGORY, language="en", service_id="poshan-ai")
        turn = advance(contact, tap("audio"), CONFIG, now=NOW)
        assert turn.session is not None
        assert turn.session.step is Step.CATEGORY


class TestDescriptionStep:
    def base(self) -> Contact:
        return at(
            Step.DESCRIPTION,
            language="en",
            service_id="anganwadi-vr",
            category_id="headset",
            display_name="Sunita",
            centre_name="AWC 42",
        )

    def test_offers_a_done_button(self) -> None:
        turn = advance(
            at(Step.CATEGORY, language="en", service_id="anganwadi-vr"),
            tap("headset"),
            CONFIG,
            now=NOW,
        )
        assert isinstance(turn.replies[0], SendButtons)
        assert turn.replies[0].buttons[0].id == "done"

    def test_photo_with_no_text_keeps_the_step_open(self) -> None:
        turn = advance(self.base(), photo(), CONFIG, now=NOW)
        assert turn.create is None
        assert turn.session is not None
        assert turn.session.step is Step.DESCRIPTION

    def test_several_messages_are_joined(self) -> None:
        contact = self.base()
        turn = advance(contact, say("headset dead"), CONFIG, now=NOW)
        contact = contact.model_copy(update={"session": turn.session})
        turn = advance(contact, say("red light stays on"), CONFIG, now=NOW)
        assert turn.session is not None
        assert turn.session.draft["description"] == "headset dead\nred light stays on"

    def test_typing_done_works_when_the_button_fails(self) -> None:
        contact = self.base()
        turn = advance(contact, say("headset dead"), CONFIG, now=NOW)
        contact = contact.model_copy(update={"session": turn.session})
        turn = advance(contact, say("Done"), CONFIG, now=NOW)
        assert turn.create is not None
        assert turn.create.description == "headset dead"


class TestIdleRescue:
    """Cloud Run has no timers between requests, so the cron finishes these."""

    def test_abandoned_description_is_completed_from_its_draft(self) -> None:
        session = Session(
            flow=Flow.REPORT,
            step=Step.DESCRIPTION,
            draft={
                "language": "hi",
                "service_id": "anganwadi-vr",
                "category_id": "headset",
                "display_name": "Sunita",
                "centre_name": "AWC 42",
                "description": "headset dead",
            },
            started_at=NOW,
            last_activity_at=NOW,
        )
        draft = finish_idle(session)
        assert draft is not None
        assert draft.description == "headset dead"

    def test_an_earlier_step_is_not_rescued(self) -> None:
        session = Session(flow=Flow.REPORT, step=Step.NAME, started_at=NOW, last_activity_at=NOW)
        assert finish_idle(session) is None

    def test_a_description_step_with_nothing_said_is_not_rescued(self) -> None:
        """No text and no ticket is better than an empty ticket."""
        session = Session(
            flow=Flow.REPORT,
            step=Step.DESCRIPTION,
            draft={"service_id": "anganwadi-vr"},
            started_at=NOW,
            last_activity_at=NOW,
        )
        assert finish_idle(session) is None
