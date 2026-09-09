"""The report flow's step machine (§7).

Pure: one turn in, replies and a new session out. Nothing here writes to
Firestore or calls Gupshup — the caller does that. The machine never holds
state in memory between messages, because Cloud Run kills idle containers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from support_service.config.models import MAX_LIST_ROWS, ConfigSnapshot
from support_service.models import Contact, Flow, InboundMessage, Language, Session, Step


@dataclass(frozen=True)
class Row:
    id: str
    label: str


@dataclass(frozen=True)
class SendText:
    body: str


@dataclass(frozen=True)
class SendList:
    body: str
    rows: tuple[Row, ...]


@dataclass(frozen=True)
class SendButtons:
    body: str
    buttons: tuple[Row, ...]


Reply = SendText | SendList | SendButtons


@dataclass(frozen=True)
class Draft:
    """Everything gathered, ready for the ticket-creation transaction."""

    language: Language
    service_id: str
    category_id: str
    display_name: str
    centre_name: str
    description: str


@dataclass(frozen=True)
class Turn:
    """The result of one inbound message."""

    replies: tuple[Reply, ...] = ()
    session: Session | None = None
    """Set only on the final step — the caller then runs the transaction."""
    create: Draft | None = None
    learned_language: Language | None = None


LANGUAGE_LABELS = {
    Language.EN: "English",
    Language.HI: "हिन्दी",
    Language.TE: "తెలుగు",
    Language.TA: "தமிழ்",
}


def begin(contact: Contact, config: ConfigSnapshot, *, now: datetime) -> Turn:
    """Open the report flow. Skips language once the contact has one."""
    if contact.language is None:
        return _ask_language(config, now=now)
    return _ask_service(contact.language, config, now=now, draft={})


def advance(
    contact: Contact,
    message: InboundMessage,
    config: ConfigSnapshot,
    *,
    now: datetime,
) -> Turn:
    """Apply one message to the contact's current step."""
    session = contact.session
    if session is None:
        return begin(contact, config, now=now)

    draft = dict(session.draft)
    language = _draft_language(draft, contact)

    handlers = {
        Step.LANGUAGE: _on_language,
        Step.SERVICE: _on_service,
        Step.NAME: _on_name,
        Step.CENTRE: _on_centre,
        Step.CATEGORY: _on_category,
        Step.DESCRIPTION: _on_description,
    }
    return handlers[session.step](contact, message, config, draft, language, now)


# --- steps ---------------------------------------------------------------


def _on_language(
    contact: Contact,
    message: InboundMessage,
    config: ConfigSnapshot,
    draft: dict[str, str],
    language: Language,
    now: datetime,
) -> Turn:
    chosen = _pick(message, [lang.value for lang in config.languages])
    if chosen is None:
        return _retry(_ask_language(config, now=now), config, language)

    picked = Language(chosen)
    draft["language"] = picked.value
    prompt = _ask_service(picked, config, now=now, draft=draft)
    return Turn(replies=prompt.replies, session=prompt.session, learned_language=picked)


def _on_service(
    contact: Contact,
    message: InboundMessage,
    config: ConfigSnapshot,
    draft: dict[str, str],
    language: Language,
    now: datetime,
) -> Turn:
    chosen = _pick(message, [service.id for service in config.enabled_services()])
    if chosen is None:
        return _retry(_ask_service(language, config, now=now, draft=draft), config, language)

    draft["service_id"] = chosen

    # Returning contacts skip name and centre — a second ticket is 3 taps, not 6.
    if contact.display_name and contact.centre_name:
        draft["display_name"] = contact.display_name
        draft["centre_name"] = contact.centre_name
        return _ask_category(language, config, now=now, draft=draft)

    return _ask(Step.NAME, "ask_name", language, config, now=now, draft=draft)


def _on_name(
    contact: Contact,
    message: InboundMessage,
    config: ConfigSnapshot,
    draft: dict[str, str],
    language: Language,
    now: datetime,
) -> Turn:
    value = _clean_text(message, 1, 80)
    if value is None:
        return _retry(
            _ask(Step.NAME, "ask_name", language, config, now=now, draft=draft), config, language
        )
    draft["display_name"] = value
    return _ask(Step.CENTRE, "ask_centre", language, config, now=now, draft=draft)


def _on_centre(
    contact: Contact,
    message: InboundMessage,
    config: ConfigSnapshot,
    draft: dict[str, str],
    language: Language,
    now: datetime,
) -> Turn:
    value = _clean_text(message, 1, 120)
    if value is None:
        return _retry(
            _ask(Step.CENTRE, "ask_centre", language, config, now=now, draft=draft),
            config,
            language,
        )
    draft["centre_name"] = value
    return _ask_category(language, config, now=now, draft=draft)


def _on_category(
    contact: Contact,
    message: InboundMessage,
    config: ConfigSnapshot,
    draft: dict[str, str],
    language: Language,
    now: datetime,
) -> Turn:
    service = config.service(draft.get("service_id", ""))
    valid = [category.id for category in service.enabled_categories()] if service else []
    chosen = _pick(message, valid)
    if chosen is None:
        return _retry(_ask_category(language, config, now=now, draft=draft), config, language)

    draft["category_id"] = chosen
    return _ask_description(language, config, now=now, draft=draft)


def _on_description(
    contact: Contact,
    message: InboundMessage,
    config: ConfigSnapshot,
    draft: dict[str, str],
    language: Language,
    now: datetime,
) -> Turn:
    """Collect text and media until Done. Media with no text is valid (§7)."""
    # Check for the finish signal first, or typing "Done" lands in the description.
    if message.reply_id == "done" or (message.text or "").strip().lower() == "done":
        return Turn(create=_to_draft(draft), session=None)

    if message.text:
        existing = draft.get("description", "")
        draft["description"] = f"{existing}\n{message.text}".strip() if existing else message.text

    # Anything else — more text, a photo — keeps the step open.
    return Turn(
        session=Session(
            flow=Flow.REPORT,
            step=Step.DESCRIPTION,
            draft=draft,
            started_at=now,
            last_activity_at=now,
        )
    )


def finish_idle(session: Session) -> Draft | None:
    """Close a `description` step abandoned past the idle window.

    Called by the 2-minute cron, not by a message. Cloud Run freezes the CPU
    between requests, so a timer inside the process would never fire.
    """
    if session.step is not Step.DESCRIPTION:
        return None
    if not session.draft.get("description"):
        return None
    return _to_draft(session.draft)


# --- prompts -------------------------------------------------------------


def _ask_language(config: ConfigSnapshot, *, now: datetime) -> Turn:
    rows = tuple(Row(lang.value, LANGUAGE_LABELS[lang]) for lang in config.languages)
    body = config.text("ask_language", Language.EN)
    return Turn(
        replies=(SendList(body, rows),),
        session=Session(flow=Flow.REPORT, step=Step.LANGUAGE, started_at=now, last_activity_at=now),
    )


def _ask_service(
    language: Language, config: ConfigSnapshot, *, now: datetime, draft: dict[str, str]
) -> Turn:
    services = config.enabled_services()[:MAX_LIST_ROWS]
    rows = tuple(Row(s.id, s.name.get(language, s.name.get(Language.EN, s.id))) for s in services)
    return Turn(
        replies=(SendList(config.text("ask_service", language), rows),),
        session=_session(Step.SERVICE, draft, now),
    )


def _ask_category(
    language: Language, config: ConfigSnapshot, *, now: datetime, draft: dict[str, str]
) -> Turn:
    service = config.service(draft.get("service_id", ""))
    categories = service.enabled_categories()[:MAX_LIST_ROWS] if service else []
    rows = tuple(
        Row(c.id, c.label.get(language, c.label.get(Language.EN, c.id))) for c in categories
    )
    return Turn(
        replies=(SendList(config.text("ask_category", language), rows),),
        session=_session(Step.CATEGORY, draft, now),
    )


def _ask_description(
    language: Language, config: ConfigSnapshot, *, now: datetime, draft: dict[str, str]
) -> Turn:
    return Turn(
        replies=(
            SendButtons(
                config.text("ask_description", language),
                (Row("done", config.text("done_button", language)),),
            ),
        ),
        session=_session(Step.DESCRIPTION, draft, now),
    )


def _ask(
    step: Step,
    key: str,
    language: Language,
    config: ConfigSnapshot,
    *,
    now: datetime,
    draft: dict[str, str],
) -> Turn:
    return Turn(
        replies=(SendText(config.text(key, language)),),
        session=_session(step, draft, now),
    )


# --- helpers -------------------------------------------------------------


def _session(step: Step, draft: dict[str, str], now: datetime) -> Session:
    return Session(flow=Flow.REPORT, step=step, draft=draft, started_at=now, last_activity_at=now)


def _pick(message: InboundMessage, valid: list[str]) -> str | None:
    """Accept a tapped row id, or a 1-based digit for phones that fail lists."""
    if message.reply_id and message.reply_id in valid:
        return message.reply_id

    raw = (message.text or "").strip()
    if raw.isdigit():
        index = int(raw) - 1
        if 0 <= index < len(valid):
            return valid[index]
    return None


def _clean_text(message: InboundMessage, low: int, high: int) -> str | None:
    value = (message.text or "").strip()
    return value if low <= len(value) <= high else None


def _retry(prompt: Turn, config: ConfigSnapshot, language: Language) -> Turn:
    """Re-send the same prompt with a nudge in front of it."""
    return Turn(
        replies=(SendText(config.text("invalid_choice", language)), *prompt.replies),
        session=prompt.session,
    )


def _draft_language(draft: dict[str, str], contact: Contact) -> Language:
    raw = draft.get("language")
    if raw:
        return Language(raw)
    return contact.language or Language.EN


def _to_draft(draft: dict[str, str]) -> Draft:
    return Draft(
        language=Language(draft.get("language", Language.EN.value)),
        service_id=draft["service_id"],
        category_id=draft["category_id"],
        display_name=draft["display_name"],
        centre_name=draft["centre_name"],
        description=draft.get("description", ""),
    )


__all__ = [
    "Draft",
    "Reply",
    "Row",
    "SendButtons",
    "SendList",
    "SendText",
    "Turn",
    "advance",
    "begin",
    "finish_idle",
]
