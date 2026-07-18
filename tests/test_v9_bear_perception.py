"""Tests pour v9_bear_perception.py — mission 2/2 baissier.

Couvre :
  - Détection fast move baissier (mocks signaux réels).
  - Détection fast move haussier.
  - correct_decision no-op si pas de fast move.
  - correct_decision avec fast bearish → boost.
  - BearAdaptiveStrategy.skip sur trend up + drift > 30 pips.
  - BearAdaptiveStrategy.compute_fast_exit avec vol haute → TP court
    et SL large.
  - Bonus : kill switch + CLI helper.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.v9.v9_bear_perception import (
    BEAR_PERCEPTION_ENV,
    BearAdaptiveStrategy,
    BearPerceptionCorrection,
    DRIFT_SKIP_THRESHOLD_PIPS,
    FAST_MOVE_BOOST,
    FAST_MOVE_THRESHOLD_PIPS_PER_MIN,
    FastMovementSignal,
    PANIC_THRESHOLD_PIPS_PER_MIN,
    TP_CEIL_PIPS,
    TP_FLOOR_PIPS,
    bear_perception_enabled,
    evaluate_decision,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _fake_m1_rows_bearish(n: int = 10, drop_per_bar: float = 0.00020) -> list[dict]:
    """Génère N bougies M1 baissières (drop cumulé = -2 pips à 10000 mult)."""
    base = 1.34000
    rows = []
    for i in range(n):
        close = base - i * drop_per_bar
        rows.append(
            {
                "id": i,
                "bar_time": 1784327100 + i * 60,
                "open": close + 0.00010,
                "high": close + 0.00015,
                "low": close - 0.00010,
                "close": close,
                "mid": close,
                "tick_volume": 100,
            }
        )
    return rows  # ordre ASC chronologique


def _fake_m1_rows_bullish(n: int = 10, rise_per_bar: float = 0.00015) -> list[dict]:
    """Génère N bougies M1 haussières."""
    base = 1.34000
    rows = []
    for i in range(n):
        close = base + i * rise_per_bar
        rows.append(
            {
                "id": i,
                "bar_time": 1784327100 + i * 60,
                "open": close - 0.00010,
                "high": close + 0.00015,
                "low": close - 0.00015,
                "close": close,
                "mid": close,
                "tick_volume": 100,
            }
        )
    return rows


def _fake_m1_rows_flat(n: int = 10) -> list[dict]:
    """Génère N bougies M1 stables (mouvement nul)."""
    rows = []
    for i in range(n):
        rows.append(
            {
                "id": i,
                "bar_time": 1784327100 + i * 60,
                "open": 1.34000,
                "high": 1.34005,
                "low": 1.33995,
                "close": 1.34000,
                "mid": 1.34000,
                "tick_volume": 100,
            }
        )
    return rows


def _row_factory(rows: list[dict]) -> list[MagicMock]:
    """Transforme une liste de dicts en liste de sqlite3.Row-like mock
    supportant ``row["key"]`` ET ``row.key``.
    """
    out = []
    for r in rows:
        m = MagicMock(spec=r)
        m.__getitem__ = lambda self, k, _r=r: _r[k]
        for k, v in r.items():
            setattr(m, k, v)
        out.append(m)
    return out


def _build_inmemory_db_with_m1(
    m1_rows_asc: list[dict],
    decision_row: dict,
    higher_tf_rows_asc: list[dict] | None = None,
    higher_tf: str = "M15",
) -> tuple[sqlite3.Connection, "Path"]:
    """Crée une DB SQLite en mémoire (fichier temporaire, sqlite3 ne
    supporte pas multi-connexion :memory:) avec le schéma
    ``forces_snapshots`` + ``decisions`` peuplés.

    Retourne (connexion, chemin) — la connexion est ouverte, l'appelant
    doit la fermer.
    """
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    conn = sqlite3.connect(str(tmp_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE forces_snapshots (
            id INTEGER PRIMARY KEY,
            snapshot_id TEXT,
            symbol TEXT,
            timeframe TEXT,
            bar_time INTEGER,
            open REAL, high REAL, low REAL, close REAL, mid REAL,
            tick_volume INTEGER,
            stale INTEGER DEFAULT 0
        );
        CREATE TABLE decisions (
            decision_id TEXT PRIMARY KEY,
            snapshot_id TEXT,
            symbol TEXT,
            timeframe TEXT,
            direction TEXT,
            confiance INTEGER,
            timestamp TEXT
        );
        """
    )
    # Insert forces_snapshots M1 (la DB attend bar_time INT).
    for r in m1_rows_asc:
        conn.execute(
            "INSERT INTO forces_snapshots (snapshot_id, symbol, timeframe, "
            "bar_time, open, high, low, close, mid, tick_volume, stale) "
            "VALUES (?, ?, 'M1', ?, ?, ?, ?, ?, ?, ?, 0)",
            (
                r["snapshot_id"] if "snapshot_id" in r else f"v9-M1-{r['bar_time']}",
                r.get("symbol", "GBPUSD"),
                r["bar_time"],
                r["open"], r["high"], r["low"], r["close"], r["mid"],
                r["tick_volume"],
            ),
        )
    if higher_tf_rows_asc:
        for r in higher_tf_rows_asc:
            conn.execute(
                "INSERT INTO forces_snapshots (snapshot_id, symbol, timeframe, "
                "bar_time, open, high, low, close, mid, tick_volume, stale) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                (
                    f"v9-{higher_tf}-{r['bar_time']}",
                    r.get("symbol", "GBPUSD"),
                    higher_tf,
                    r["bar_time"],
                    r["open"], r["high"], r["low"], r["close"], r["mid"],
                    r["tick_volume"],
                ),
            )
    conn.execute(
        "INSERT INTO decisions (decision_id, snapshot_id, symbol, timeframe, "
        "direction, confiance, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            decision_row["decision_id"],
            decision_row["snapshot_id"],
            decision_row["symbol"],
            decision_row["timeframe"],
            decision_row["direction"],
            decision_row.get("confiance", 50),
            decision_row.get("timestamp", "2026-07-17T20:00:00+00:00"),
        ),
    )
    conn.commit()
    return conn, tmp_path


# ── Tests BearPerceptionCorrection ────────────────────────────────────


def test_detect_fast_movement_baissier() -> None:
    """Un mouvement baissier rapide (≥ 1 pips/min sur 10 bougies) doit
    être détecté comme fast_move=True."""
    # DB in-memory avec 10 bougies M1 baissières rapides (drop -2.5 pips/bar).
    m1_rows = _fake_m1_rows_bearish(10, drop_per_bar=0.00025)
    # bar_time de la décision = la bougie la plus récente.
    decision_bar_time = m1_rows[-1]["bar_time"]
    decision_row = {
        "decision_id": "dec_test_bear",
        "snapshot_id": f"v9-GBPUSD-M15-{decision_bar_time}-000999",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "baissiere",
        "confiance": 80,
        "timestamp": "2026-07-17T20:00:00+00:00",
    }
    # Bougies M15 très lissées (1 seule direction).
    m15_rows = []
    base_m15 = 1.34000
    for i in range(6):
        m15_rows.append(
            {
                "bar_time": decision_bar_time - (5 - i) * 900,  # 15 min apart
                "open": base_m15,
                "high": base_m15 + 0.00010,
                "low": base_m15 - 0.00010,
                "close": base_m15 - i * 0.00005,  # M15 lissé ~0.05 pips/15min
                "mid": base_m15 - i * 0.00005,
                "tick_volume": 100,
            }
        )
    conn, db_path = _build_inmemory_db_with_m1(
        m1_rows, decision_row, higher_tf_rows_asc=m15_rows, higher_tf="M15",
    )
    conn.close()

    corrector = BearPerceptionCorrection(db_path=db_path)
    signal = corrector.detect_fast_movement(
        symbol="GBPUSD", decision_id="dec_test_bear",
    )

    try:
        assert isinstance(signal, FastMovementSignal)
        assert signal.is_fast_move is True, (
            f"attendu fast_move=True (speed={signal.speed_pips_per_min}, "
            f"mag=signal.m1_signal_strength)"
        )
        assert signal.direction == "baissiere"
        assert signal.speed_pips_per_min < 0
        assert abs(signal.speed_pips_per_min) >= FAST_MOVE_THRESHOLD_PIPS_PER_MIN
        assert signal.n_confirmations >= 5
    finally:
        try:
            db_path.unlink()
        except OSError:
            pass


def test_detect_fast_movement_haussier() -> None:
    """Un mouvement haussier rapide doit être détecté et ne PAS
    déclencher de boost baissier."""
    m1_rows = _fake_m1_rows_bullish(10, rise_per_bar=0.00030)
    decision_bar_time = m1_rows[-1]["bar_time"]
    decision_row = {
        "decision_id": "dec_test_bull",
        "snapshot_id": f"v9-GBPUSD-M15-{decision_bar_time}-000998",
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "direction": "haussiere",
        "confiance": 75,
        "timestamp": "2026-07-17T20:00:00+00:00",
    }
    conn, db_path = _build_inmemory_db_with_m1(
        m1_rows, decision_row,
    )
    conn.close()

    corrector = BearPerceptionCorrection(db_path=db_path)
    signal = corrector.detect_fast_movement(
        symbol="GBPUSD", decision_id="dec_test_bull",
    )

    try:
        assert signal.is_fast_move is True
        assert signal.direction == "haussiere"
        assert signal.speed_pips_per_min > 0
    finally:
        try:
            db_path.unlink()
        except OSError:
            pass


def test_correct_decision_no_fast_move() -> None:
    """Si pas de fast move, correct_decision est un no_op + ajoute
    les métadonnées bear_perception_* sans modifier la confiance."""
    corrector = BearPerceptionCorrection(db_path=":memory:")

    # Mock : on injecte un signal plat (pas de fast_move).
    flat_signal = FastMovementSignal(
        is_fast_move=False,
        speed_pips_per_min=0.0,
        direction="neutre",
        confidence=0.0,
        m1_signal_strength=0.0,
        higher_tf_speed=0.0,
        divergence_ratio=None,
        is_panic=False,
        n_confirmations=0,
    )

    decision = {
        "decision_id": "dec_test_flat",
        "symbol": "GBPUSD",
        "direction": "baissiere",
        "confiance": 60,
        "snapshot_id": "v9-GBPUSD-M15-1784327400-000999",
    }

    with patch.object(
        corrector, "detect_fast_movement", return_value=flat_signal,
    ):
        result = corrector.correct_decision(dict(decision))

    assert result["confiance"] == 60  # inchangé
    assert "bear_perception_signal" in result
    assert result["bear_perception_status"] == "evaluated"
    # Pas de boost, pas de divergence warning.
    assert result["bear_perception_correction"] == "no_op"


def test_correct_decision_with_fast_bearish() -> None:
    """Si fast_move baissier détecté + décision baissière, la
    confiance doit recevoir un boost (+FAST_MOVE_BOOST, plafond 100)."""
    corrector = BearPerceptionCorrection(db_path=":memory:")

    bear_signal = FastMovementSignal(
        is_fast_move=True,
        speed_pips_per_min=-2.5,
        direction="baissiere",
        confidence=0.8,
        m1_signal_strength=2.5,
        higher_tf_speed=-0.5,
        divergence_ratio=5.0,
        is_panic=True,
        n_confirmations=8,
    )

    decision = {
        "decision_id": "dec_test_boost",
        "symbol": "GBPUSD",
        "direction": "baissiere",
        "confiance": 80,
        "snapshot_id": "v9-GBPUSD-M15-1784327400-000999",
    }

    with patch.object(
        corrector, "detect_fast_movement", return_value=bear_signal,
    ):
        result = corrector.correct_decision(dict(decision))

    assert result["confiance"] == min(100, 80 + FAST_MOVE_BOOST)
    assert result["bear_perception_correction"] == "boost_bear_momentum"
    assert "panic" in result["bear_perception_reason"].lower()
    assert "fast_move_baissier_detected" in result["bear_perception_reason"]


def test_correct_decision_caps_at_100() -> None:
    """Le boost ne doit jamais dépasser 100 (cap dur)."""
    corrector = BearPerceptionCorrection(db_path=":memory:")

    bear_signal = FastMovementSignal(
        is_fast_move=True,
        speed_pips_per_min=-2.5,
        direction="baissiere",
        confidence=0.9,
        m1_signal_strength=2.5,
        higher_tf_speed=-0.5,
        divergence_ratio=5.0,
        is_panic=True,
        n_confirmations=9,
    )

    decision = {
        "decision_id": "dec_test_cap",
        "symbol": "GBPUSD",
        "direction": "baissiere",
        "confiance": 98,
        "snapshot_id": "v9-GBPUSD-M15-1784327400-000999",
    }

    with patch.object(
        corrector, "detect_fast_movement", return_value=bear_signal,
    ):
        result = corrector.correct_decision(dict(decision))

    assert result["confiance"] == 100  # plafonné
    assert result["bear_perception_correction"] == "boost_bear_momentum"


def test_correct_decision_handles_missing_symbol() -> None:
    """R6 — décision sans symbol → pas de crash, status=skipped."""
    corrector = BearPerceptionCorrection(db_path=":memory:")
    decision = {"direction": "baissiere", "confiance": 50}  # pas de symbol/id
    result = corrector.correct_decision(dict(decision))
    assert result["bear_perception_status"] == "skipped"
    assert "missing_symbol_or_id" in result["bear_perception_reason"]


# ── Tests BearAdaptiveStrategy ────────────────────────────────────────


def test_bear_strategy_skip_trend_up() -> None:
    """Trend haussière forte (drift > 30 pips/jour OU h1_dir haussière)
    → skip du trade baissier."""
    strategy = BearAdaptiveStrategy()

    decision = {"direction": "baissiere", "confiance": 80}

    # Cas 1 : drift > 30 pips/jour.
    ctx_drift = {"drift_pips_per_day": 35.0}
    assert strategy.should_skip_bearish(decision, ctx_drift) is True

    # Cas 2 : H1 haussière.
    ctx_h1 = {"h1_dir": "HAUSSIERE"}
    assert strategy.should_skip_bearish(decision, ctx_h1) is True

    # Cas 3 : regime EXTENSION haussière.
    ctx_ext = {"regime_type": "EXTENSION", "regime_direction": "HAUSSIERE"}
    assert strategy.should_skip_bearish(decision, ctx_ext) is True

    # Cas 4 : vol LOW (pas de momentum).
    ctx_vol = {"vol_regime": "LOW"}
    assert strategy.should_skip_bearish(decision, ctx_vol) is True

    # Cas 5 : trade haussière → pas un trade baissier, no-skip.
    bull_decision = {"direction": "haussiere", "confiance": 80}
    assert strategy.should_skip_bearish(bull_decision, ctx_drift) is False

    # Cas 6 : contexte neutre → no-skip.
    ctx_neutral = {"drift_pips_per_day": 10.0}
    assert strategy.should_skip_bearish(decision, ctx_neutral) is False

    # Cas 7 : drift juste sous le seuil.
    ctx_below = {"drift_pips_per_day": DRIFT_SKIP_THRESHOLD_PIPS - 0.1}
    assert strategy.should_skip_bearish(decision, ctx_below) is False


def test_bear_strategy_compute_fast_exit_vol_high() -> None:
    """compute_fast_exit(vol_pips=5) doit raccourcir le TP et élargir
    le SL par rapport aux defaults."""
    strategy = BearAdaptiveStrategy(max_hold_bars=8, fast_tp=4.0, fast_sl=12.0)

    base = strategy.compute_fast_exit(vol_pips=0.0)
    high_vol = strategy.compute_fast_exit(vol_pips=5.0)

    # TP raccourci (vol haute).
    assert high_vol["tp_pips"] < base["tp_pips"]
    assert high_vol["tp_pips"] >= TP_FLOOR_PIPS
    # SL élargi (laisser respirer).
    assert high_vol["sl_pips"] > base["sl_pips"]
    # TimeExit raccourci.
    assert high_vol["max_hold_bars"] <= base["max_hold_bars"]
    # Bornes respectées.
    assert TP_FLOOR_PIPS <= high_vol["tp_pips"] <= TP_CEIL_PIPS
    assert high_vol["exit_strategy"] == "FAST_TP_SL"


def test_bear_strategy_compute_fast_exit_vol_zero() -> None:
    """vol_pips=0 → retour aux defaults (TP=fast_tp, SL=fast_sl)."""
    strategy = BearAdaptiveStrategy(max_hold_bars=8, fast_tp=4.0, fast_sl=12.0)
    out = strategy.compute_fast_exit(vol_pips=0.0)
    assert out["tp_pips"] == 4.0
    assert out["sl_pips"] == 12.0
    assert out["max_hold_bars"] == 8


def test_bear_strategy_compute_fast_exit_clamped() -> None:
    """vol_pips très élevé → TP plancher, SL plafond, time plancher."""
    strategy = BearAdaptiveStrategy()
    out = strategy.compute_fast_exit(vol_pips=9999.0)
    assert out["tp_pips"] == TP_FLOOR_PIPS
    assert out["sl_pips"] >= 8.0
    assert out["max_hold_bars"] >= 2


# ── Tests kill switch + evaluate_decision ─────────────────────────────


def test_kill_switch_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le kill switch est OFF par défaut (R25')."""
    monkeypatch.delenv(BEAR_PERCEPTION_ENV, raising=False)
    assert bear_perception_enabled() is False
    monkeypatch.setenv(BEAR_PERCEPTION_ENV, "1")
    assert bear_perception_enabled() is True


def test_evaluate_decision_handles_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """evaluate_decision avec un decision_id inexistant → status=error
    (R6 : pas de crash)."""
    # DB vide en mémoire, donc decision_introuvable.
    tmp_db = Path(":memory:")
    # sqlite3.connect(":memory:") crée une connexion isolée — pas un
    # path réel. evaluate_decision utilise Path(db_path) → on triche
    # via un fichier temporaire.
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        result = evaluate_decision(
            decision_id="dec_inexistant", db_path=tmp_path,
        )
        assert result["status"] == "error"
        assert "decision_not_found" in result["reason"]
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


def test_compute_m1_speed_pure_function() -> None:
    """Test direct de la fonction pure _compute_m1_speed.

    La fonction attend les rows en ordre DESC (résultat de query SQL).
    On inverse donc les fake_rows avant de les passer.
    """
    # _fake_m1_rows_bearish renvoie en ordre ASC chronologique.
    # La fonction _compute_m1_speed applique [::-1] en interne → on
    # doit donc lui passer en DESC.
    rows_asc = _fake_m1_rows_bearish(10, drop_per_bar=0.00025)
    rows_desc = list(reversed(rows_asc))
    rows = _row_factory(rows_desc)
    speed_signed, magnitude, n_conf, direction = (
        BearPerceptionCorrection._compute_m1_speed(rows, "GBPUSD")
    )
    assert direction == "baissiere"
    assert speed_signed < 0
    # drop_per_bar=0.00025 × 10000 = 2.5 pips/bar → speed ~2.5 pips/min
    assert abs(speed_signed) >= 2.0
    assert n_conf >= 9  # toutes les bougies baissières


def test_compute_m1_speed_handles_empty() -> None:
    """_compute_m1_speed retourne (0, 0, 0, 'neutre') sur liste vide."""
    speed_signed, magnitude, n_conf, direction = (
        BearPerceptionCorrection._compute_m1_speed([], "GBPUSD")
    )
    assert speed_signed == 0.0
    assert magnitude == 0.0
    assert n_conf == 0
    assert direction == "neutre"


def test_extract_bar_time() -> None:
    """Le parsing de bar_time depuis snapshot_id est correct et défensif."""
    extractor = BearPerceptionCorrection._extract_bar_time
    assert extractor("v9-GBPUSD-M15-1784327404-000303") == 1784327404
    assert extractor(None) is None
    assert extractor("") is None
    assert extractor("invalid") is None
    # bar_time avec moins de 8 chiffres → None (parsing strict).
    assert extractor("v9-GBPUSD-M15-123-000303") is None
