"""Tests — JOURNAL COGNITIF (core/v9/cognitive_journal.py + scripts/v9_cognitive.py)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v9 import cognitive_journal  # noqa: E402
from scripts import v9_cognitive  # noqa: E402


@pytest.fixture
def journal_db(tmp_path: Path) -> Path:
    return tmp_path / "cognitive_test.db"


@pytest.fixture
def no_market_db() -> Path:
    """DB marché absente — memory_query dégrade gracieusement (dict/liste vide)."""
    return Path("no_such_market.db")


def test_log_v9_reading_creates_row(journal_db: Path, no_market_db: Path) -> None:
    reading_id = cognitive_journal.log_v9_reading(market_db_path=no_market_db, db_path=journal_db)
    assert isinstance(reading_id, int)

    reading = cognitive_journal.get_reading(reading_id, db_path=journal_db)
    assert reading is not None
    assert reading["source"] == "v9"
    assert reading["v9_narrative"]
    assert reading["son_correction"] is None


def test_log_son_correction_updates_row(journal_db: Path, no_market_db: Path) -> None:
    reading_id = cognitive_journal.log_v9_reading(market_db_path=no_market_db, db_path=journal_db)

    cognitive_journal.log_son_correction(
        reading_id, "JPY faible aussi", "baissiere", ["JPY_WATCH"], db_path=journal_db
    )

    reading = cognitive_journal.get_reading(reading_id, db_path=journal_db)
    assert reading is not None
    assert reading["son_correction"] == "JPY faible aussi"
    assert reading["direction_son"] == "baissiere"
    assert "JPY_WATCH" in reading["patterns_son"]

    corrections = cognitive_journal.get_pending_corrections(db_path=journal_db)
    assert corrections == []  # la lecture n'est plus en attente


def test_get_pending_corrections_returns_list(journal_db: Path, no_market_db: Path) -> None:
    assert cognitive_journal.get_pending_corrections(db_path=journal_db) == []

    id_1 = cognitive_journal.log_v9_reading(market_db_path=no_market_db, db_path=journal_db)
    id_2 = cognitive_journal.log_v9_reading(market_db_path=no_market_db, db_path=journal_db)

    pending = cognitive_journal.get_pending_corrections(limit=5, db_path=journal_db)
    assert isinstance(pending, list)
    assert [r["id"] for r in pending] == [id_1, id_2]  # plus anciennes d'abord

    cognitive_journal.log_son_correction(id_1, "vu", "haussiere", None, db_path=journal_db)
    pending_after = cognitive_journal.get_pending_corrections(db_path=journal_db)
    assert [r["id"] for r in pending_after] == [id_2]


def test_learn_from_corrections_creates_lesson(journal_db: Path, no_market_db: Path) -> None:
    assert cognitive_journal.get_lessons(db_path=journal_db) == []

    for _ in range(3):
        reading_id = cognitive_journal.log_v9_reading(market_db_path=no_market_db, db_path=journal_db)
        cognitive_journal.log_son_correction(
            reading_id, "attention au JPY", None, ["JPY_WATCH"], db_path=journal_db
        )

    created = cognitive_journal.learn_from_corrections(db_path=journal_db)
    assert len(created) == 1
    assert "JPY_WATCH" in created[0]["rule"]

    lessons = cognitive_journal.get_lessons(confidence_min=0.3, db_path=journal_db)
    assert len(lessons) == 1
    assert lessons[0]["confidence"] >= 0.3

    assert cognitive_journal.get_lessons(confidence_min=0.99, db_path=journal_db) == []


def test_cognitive_cli_log_exits_zero(
    journal_db: Path, no_market_db: Path, capsys: pytest.CaptureFixture
) -> None:
    rc = v9_cognitive.main(["--log", "--db", str(journal_db), "--market-db", str(no_market_db)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "LECTURE V9" in captured.out


def test_cognitive_cli_pending_handles_empty(
    journal_db: Path, capsys: pytest.CaptureFixture
) -> None:
    rc = v9_cognitive.main(["--pending", "--db", str(journal_db)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "Aucune lecture" in captured.out
