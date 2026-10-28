"""The centre sheet is the source of truth; the importer refuses a broken one."""

from __future__ import annotations

from pathlib import Path

import pytest

from support_service.centres import read_centres

HEADER = "centre_id,block,block_en,village,village_en,worker_phone\n"


def _sheet(tmp_path: Path, body: str, header: str = HEADER) -> Path:
    path = tmp_path / "centres.csv"
    path.write_text(header + body, encoding="utf-8")
    return path


def test_reads_rows_and_normalises_ids_and_phones(tmp_path: Path) -> None:
    rows = read_centres(
        _sheet(tmp_path, "ngp-awc-001,रामटेक,Ramtek,शिवणीटोला,Shivanitola,98765 43210\n")
    )
    assert rows == [
        {
            "centre_id": "NGP-AWC-001",
            "block": "रामटेक",
            "block_en": "Ramtek",
            "village": "शिवणीटोला",
            "village_en": "Shivanitola",
            "worker_phone": "919876543210",
        }
    ]


def test_the_repo_sheet_has_66_distinct_centres() -> None:
    rows = read_centres(Path(__file__).parent.parent / "data" / "centres.csv")
    assert len(rows) == 66
    assert len({row["centre_id"] for row in rows}) == 66


def test_rejects_a_duplicate_id(tmp_path: Path) -> None:
    sheet = _sheet(tmp_path, "NGP-AWC-001,a,a,b,b,\nNGP-AWC-001,c,c,d,d,\n")
    with pytest.raises(ValueError, match="duplicate"):
        read_centres(sheet)


def test_rejects_a_sheet_without_the_required_columns(tmp_path: Path) -> None:
    sheet = _sheet(tmp_path, "NGP-AWC-001,a\n", header="centre_id,block\n")
    with pytest.raises(ValueError, match="missing columns"):
        read_centres(sheet)
