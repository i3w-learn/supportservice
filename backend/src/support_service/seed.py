"""Write seed data to Firestore. Run once at setup, idempotent."""

from support_service.config.defaults import COPY, SERVICES, seed
from support_service.firestore import get_db, to_firestore


def run_seed() -> None:
    db = get_db()

    for service in SERVICES:
        db.collection("services").document(service.id).set(to_firestore(service.model_dump()))

    for lang, strings in COPY.items():
        db.collection("config").document("copy").collection(lang.value).document("strings").set(
            strings
        )

    config = seed()
    db.collection("config").document("settings").set(to_firestore(config.settings.model_dump()))

    db.collection("config").document("languages").set(
        {lang.value: True for lang in config.languages}
    )

    print(f"Seeded {len(SERVICES)} services, {len(COPY)} language packs, settings")


if __name__ == "__main__":
    run_seed()
