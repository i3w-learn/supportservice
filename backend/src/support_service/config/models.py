"""Categories and bot copy — config as data, not code (§5).

Adding a category is a Firestore document. Changing a string is a write, not a
deploy. Steps take a `ConfigSnapshot` as an argument so they stay pure and
testable without Firestore.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from support_service.models import Language

# WhatsApp interactive lists cap at 10 rows. The API rejects the 11th (§5).
MAX_LIST_ROWS = 10


class Category(BaseModel):
    id: str
    label: dict[Language, str]
    order: int = 0
    enabled: bool = True


class Settings(BaseModel):
    sla_reminder_hours: int = 24
    sla_breach_hours: int = 48
    whatsapp_window_hours: int = 24
    session_expiry_hours: int = 24
    media_idle_seconds: int = 90
    retention_days: int = 365


class ConfigSnapshot(BaseModel):
    """Everything the bot needs to run one turn, read once per request."""

    categories: list[Category] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=lambda: list(Language))
    # Named `strings`, not `copy` — Pydantic's BaseModel already has `.copy()`.
    # Stored under `config/copy/{lang}` in Firestore regardless (§5).
    strings: dict[Language, dict[str, str]] = Field(default_factory=dict)
    settings: Settings = Field(default_factory=Settings)

    def enabled_categories(self) -> list[Category]:
        return sorted(
            (category for category in self.categories if category.enabled),
            key=lambda category: category.order,
        )

    def category_label(self, category_id: str, language: Language) -> str:
        category = next((c for c in self.categories if c.id == category_id), None)
        if category is None:
            return category_id
        return category.label.get(language) or category.label.get(Language.EN) or category_id

    def text(self, key: str, language: Language) -> str:
        """Bot copy, falling back to English then to the key itself.

        A missing string must never crash a conversation — the user gets an
        untranslated line, which is recoverable; an exception is not.
        """
        for candidate in (language, Language.EN):
            value = self.strings.get(candidate, {}).get(key)
            if value:
                return value
        return key
