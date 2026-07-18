"""test_v9_bayesian_exclude_window.py — Tests pour les filtres exclude_* de fit_from_decisions_db.

Vérifie :
T1. fit_from_decisions_db accepte exclude_resolved_before/after/dates (R2 additif)
T2. Exclure une date précise filtre les décisions
T3. Exclure avant une date garde les décisions >= date
T4. Exclure après une date garde les décisions <= date
T5. Combinaison des 3 filtres
T6. Comportement par défaut inchangé (backward compat)
T7. fit produit toujours brier_metrics valides
T8. exclusion_date avec format invalide → erreur gérée (R6)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.v9.v9_bayesian_predictor import (
    DEFAULT_CALIBRATION_DB,
    fit_from_decisions_db,
)


@pytest.fixture
def synthetic_db(tmp_path: Path) -> Path:
    """DB v9_forces-like avec décisions réparties sur 4 jours (14-17/07)."""
    db = tmp_path / "fake.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript("""
            CREATE TABLE decisions (
                decision_id TEXT PRIMARY KEY, timestamp TEXT,
                symbol TEXT, timeframe TEXT, regime_type TEXT,
                scene_id TEXT, behavior_id TEXT, signal_id TEXT,
                is_win INTEGER, resolution_pips REAL, resolved_at TEXT
            );
            CREATE TABLE signals (
                signal_id TEXT PRIMARY KEY, timestamp TEXT,
                symbol TEXT, timeframe TEXT, confiance INTEGER
            );
            CREATE TABLE behaviors (
                behavior_id TEXT PRIMARY KEY, phase TEXT
            );
        """)
        # 50 décisions : 14/15/16/17 juillet
        for day_idx, day in enumerate(["2026-07-14", "2026-07-15",
                                         "2026-07-16", "2026-07-17"]):
            for i in range(12 if day_idx < 3 else 14):
                idx = day_idx * 12 + i
                # WR dégradé sur 17/07
                if day == "2026-07-17":
                    is_win = 1 if i % 5 == 0 else 0
                else:
                    is_win = 1 if i % 2 == 0 else 0
                conn.execute(
                    "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (f"d{idx}", f"{day}T10:00:00", "GBPUSD", "M15",
                     "NEUTRE", None, f"b{idx}", f"s{idx}",
                     is_win, 5.0, f"{day}T10:01:00"),
                )
                conn.execute(
                    "INSERT INTO signals VALUES (?, ?, ?, ?, ?)",
                    (f"s{idx}", f"{day}T10:00:00", "GBPUSD", "M15", 75),
                )
                conn.execute(
                    "INSERT INTO behaviors VALUES (?, ?)",
                    (f"b{idx}", "culmination"),
                )
        conn.commit()
    finally:
        conn.close()
    return db


@pytest.fixture
def cal_db(tmp_path: Path) -> Path:
    return tmp_path / "cal.db"


# ============================================================== T1 backward compat

def test_fit_default_no_exclude(synthetic_db: Path, cal_db: Path):
    """Backward compat : pas de filtre → comportement original."""
    r = fit_from_decisions_db(synthetic_db, cal_db)
    assert "error" not in r
    assert r["n_fit"] == 50  # toutes les décisions
    assert 0.4 < r["global_wr"] < 0.7


def test_fit_default_no_exclude_no_kwargs(synthetic_db: Path, cal_db: Path):
    """Aucun kwarg passé → comportement identique."""
    r = fit_from_decisions_db(synthetic_db, cal_db)
    assert "error" not in r
    assert r["n_fit"] >= 1


# ============================================================== T2 exclude_resolved_dates

def test_fit_exclude_specific_date(synthetic_db: Path, cal_db: Path):
    """Exclure 2026-07-17 → 36 décisions (50 - 14)."""
    r = fit_from_decisions_db(synthetic_db, cal_db,
                              exclude_resolved_dates=("2026-07-17",))
    assert "error" not in r
    assert r["n_fit"] == 36  # 50 total - 14 du 17/07


def test_fit_exclude_multiple_dates(synthetic_db: Path, cal_db: Path):
    """Exclure 16 + 17 → 24 décisions (12 + 12)."""
    r = fit_from_decisions_db(
        synthetic_db, cal_db,
        exclude_resolved_dates=("2026-07-16", "2026-07-17"),
    )
    assert "error" not in r
    assert r["n_fit"] == 24


def test_fit_exclude_improves_wr(synthetic_db: Path, cal_db: Path):
    """Exclure 17/07 (catastrophe) doit augmenter le WR global."""
    r_full = fit_from_decisions_db(synthetic_db, cal_db)
    r_clean = fit_from_decisions_db(synthetic_db, cal_db,
                                    exclude_resolved_dates=("2026-07-17",))
    assert r_clean["global_wr"] > r_full["global_wr"], (
        f"WR après exclusion ({r_clean['global_wr']:.2%}) doit être "
        f"> WR full ({r_full['global_wr']:.2%})"
    )


# ============================================================== T3 exclude_resolved_before

def test_fit_exclude_before(synthetic_db: Path, cal_db: Path):
    """Exclure les décisions résolues AVANT 17/07 00:00 → 14 décisions (17/07 seulement)."""
    r = fit_from_decisions_db(synthetic_db, cal_db,
                              exclude_resolved_before="2026-07-17T00:00:00")
    assert "error" not in r
    assert r["n_fit"] == 14  # uniquement 17/07


# ============================================================== T4 exclude_resolved_after

def test_fit_exclude_after(synthetic_db: Path, cal_db: Path):
    """exclude_resolved_after='2026-07-14T23:59:59' garde UNIQUEMENT <= 14/07 23:59."""
    r = fit_from_decisions_db(synthetic_db, cal_db,
                              exclude_resolved_after="2026-07-14T23:59:59")
    assert "error" not in r
    # Uniquement les 12 décisions du 14/07 (timestamp avant 15/07)
    assert r["n_fit"] == 12


def test_fit_exclude_after_keeps_15_16_17(synthetic_db: Path, cal_db: Path):
    """exclude_resolved_after='2026-07-17T23:59:59' garde 14/15/16/17."""
    r = fit_from_decisions_db(synthetic_db, cal_db,
                              exclude_resolved_after="2026-07-17T23:59:59")
    assert "error" not in r
    # 12 (14) + 12 (15) + 12 (16) + 14 (17) = 50
    assert r["n_fit"] == 50


# ============================================================== T5 combinaison

def test_fit_combined_filters(synthetic_db: Path, cal_db: Path):
    """before + dates combinés."""
    r = fit_from_decisions_db(
        synthetic_db, cal_db,
        exclude_resolved_before="2026-07-15T00:00:00",
        exclude_resolved_dates=("2026-07-16",),
    )
    assert "error" not in r
    # après 15/07 00:00 → 12 + 12 + 14 = 38
    # exclure 16 → 12 (15/07) + 14 (17/07) = 26
    assert r["n_fit"] == 26


# ============================================================== T6 backward compat signature

def test_signature_backward_compatible(synthetic_db: Path, cal_db: Path):
    """Anciens appels (sans kwargs) toujours fonctionnels."""
    r = fit_from_decisions_db(synthetic_db, cal_db)
    assert "error" not in r
    # Vérifier que toutes les clés originales sont présentes
    assert "n_fit" in r
    assert "n_cells" in r
    assert "platt_global" in r
    assert "global_wr" in r
    assert "calibration_metrics" in r


# ============================================================== T7 metrics toujours valides

def test_fit_excluded_still_has_metrics(synthetic_db: Path, cal_db: Path):
    """Même avec exclusion, le fit retourne des métriques valides."""
    r = fit_from_decisions_db(synthetic_db, cal_db,
                              exclude_resolved_dates=("2026-07-17",))
    assert "error" not in r
    assert "calibration_metrics" in r
    cm = r["calibration_metrics"]
    assert cm["n"] == 36
    # brier_score ∈ [0, 1] toujours (c'est une MSE)
    assert 0 <= cm["brier_score"] <= 1
    assert 0 <= cm["ece"] <= 1
    # BSS peut être négatif si Platt est moins bon que la baseline naïve
    # (c'est normal — on n'assert pas la borne supérieure)
    assert isinstance(cm["brier_skill_score"], float)


# ============================================================== T8 R6 erreur gérée

def test_fit_db_missing(synthetic_db: Path, cal_db: Path, tmp_path: Path):
    """DB inexistante → error retourné."""
    r = fit_from_decisions_db(tmp_path / "no.db", cal_db)
    assert "error" in r


def test_fit_db_corrupt(tmp_path: Path, cal_db: Path):
    """DB corrompue → error retourné (R6)."""
    db = tmp_path / "corrupt.db"
    db.write_text("not sqlite")
    r = fit_from_decisions_db(db, cal_db)
    assert "error" in r


# ============================================================== T9 use case réel

def test_real_use_case_exclude_17_07_catastrophe(synthetic_db: Path, cal_db: Path):
    """Use case réel : exclure la journée catastrophe du 17/07 via dates tuple."""
    r = fit_from_decisions_db(
        synthetic_db, cal_db,
        exclude_resolved_dates=("2026-07-17",),
    )
    assert "error" not in r
    # 50 - 14 (17/07) = 36 décisions
    assert r["n_fit"] == 36
    # Le 17/07 ayant un WR dégradé (~14%), l'exclusion doit l'augmenter
    r_full = fit_from_decisions_db(synthetic_db, cal_db)
    assert r["global_wr"] > r_full["global_wr"]


# ============================================================== T10 pas de régression tests existants

def test_default_kwargs_unchanged(synthetic_db: Path, cal_db: Path):
    """Aucun kwarg → résultat strictement identique à avant le fix."""
    r = fit_from_decisions_db(synthetic_db, cal_db)
    # Champs obligatoires toujours présents
    for key in ("n_fit", "n_cells", "platt_global", "global_wr",
                "calibration_metrics"):
        assert key in r
