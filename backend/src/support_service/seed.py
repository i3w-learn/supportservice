"""Write seed data to Firestore. Run once at setup, idempotent."""

import os

from support_service.config.defaults import CATEGORIES, COPY, seed
from support_service.controllers.auth_controller import hash_password
from support_service.repositories.base import get_db, to_firestore


def run_seed() -> None:
    db = get_db()

    for category in CATEGORIES:
        db.collection("categories").document(category.id).set(to_firestore(category.model_dump()))

    for lang, strings in COPY.items():
        db.collection("config").document("copy").collection(lang.value).document("strings").set(
            strings
        )

    config = seed()
    db.collection("config").document("settings").set(to_firestore(config.settings.model_dump()))

    db.collection("config").document("languages").set(
        {lang.value: True for lang in config.languages}
    )

    admin_email = os.environ.get("SEED_ADMIN_EMAIL", "")
    admin_password = os.environ.get("SEED_ADMIN_PASSWORD", "")
    if admin_email and admin_password:
        db.collection("admins").document("admin-001").set(
            {
                "email": admin_email,
                "passwordHash": hash_password(admin_password),
                "displayName": os.environ.get("SEED_ADMIN_NAME", "Admin"),
            }
        )
        print(f"  Admin: {admin_email}")

    print(f"Seeded {len(CATEGORIES)} categories, {len(COPY)} language packs, settings, 1 admin")


if __name__ == "__main__":
    run_seed()
