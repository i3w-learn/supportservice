"""Import the Anganwadi centre master list into Firestore.

    uv run python -m support_service.centres data/centres.csv

One document per row in `centres/{centre_id}`. Columns become fields, so a
new column in the sheet (worker phone, smart-board serial, warranty date)
needs no code change. Writes merge, so fields edited by hand in Firestore
that the sheet does not have survive a re-import. Run it again whenever the
sheet changes.
"""

from __future__ import annotations

import csv
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from support_service.repositories.base import get_db, to_firestore
from support_service.repositories.centre_repository import centre_ref

REQUIRED = ("centre_id", "block", "block_en", "village", "village_en")


def read_centres(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"{path} has no rows")
    missing = [column for column in REQUIRED if column not in rows[0]]
    if missing:
        raise ValueError(f"{path} is missing columns: {', '.join(missing)}")

    seen: set[str] = set()
    centres: list[dict[str, Any]] = []
    for row in rows:
        centre_id = (row.get("centre_id") or "").strip().upper()
        if not centre_id:
            raise ValueError(f"row {len(centres) + 1} has no centre_id")
        if centre_id in seen:
            raise ValueError(f"duplicate centre_id {centre_id}")
        seen.add(centre_id)
        clean = {key: (value or "").strip() for key, value in row.items() if key}
        clean["centre_id"] = centre_id
        # Phones are matched against WhatsApp numbers, which are digits only.
        if clean.get("worker_phone"):
            digits = "".join(ch for ch in clean["worker_phone"] if ch.isdigit())
            clean["worker_phone"] = digits if digits.startswith("91") else f"91{digits}"
        centres.append(clean)
    return centres


def import_centres(path: Path) -> int:
    db = get_db()
    now = datetime.now(UTC)
    rows = read_centres(path)
    for row in rows:
        centre_ref(db, row["centre_id"]).set(to_firestore({**row, "updated_at": now}), merge=True)
    return len(rows)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python -m support_service.centres <centres.csv>", file=sys.stderr)
        sys.exit(2)
    count = import_centres(Path(sys.argv[1]))
    print(f"Imported {count} centres")
