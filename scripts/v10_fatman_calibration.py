#!/usr/bin/env python
"""V10 Fatman Live Calibration — Align FatmanCalculator vs Oracle on 10 recent signals.

MISSION P0: Calibration Live Fatman
- Charge 10 signaux récents depuis forces_snapshots (M30/H1/H4)
- Pour chaque signal : compare FatmanLiveState (DB reader) vs Oracle (Hawkeye)
- Rapport d'alignement : agreement score, breakdown par composant
- R9 audit trail complet

Doctrine: R1-AGIR, R3-INVENTER, R9-AUDIT, R10-CAPITAL, R7-TESTS VERTS
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_fatman_db_reader import (  # noqa: E402
    FatmanLiveState,
    FatmanSource,
    Momentum,
    get_fatman_live,
    get_all_fatman_live,
    DEFAULT_DB_PATH,
)
from scripts.fatman_oracle import (  # noqa: E402
    FatmanSetup,
    FatmanVerdict,
    oracle_fatman,
    FATMAN_HAWKEYE_RULES,
    ACTIVE_FATMAN_SESSIONS,
)

log = logging.getLogger(__name__)

PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]
TIMEFRAMES = ["M30", "H1", "H4"]


@dataclass
class CalibrationSignal:
    """Un signal de calibration (DB snapshot + setup construit)."""
    symbol: str
    timeframe: str
    timestamp: str
    bar_time: int
    open: float
    high: float
    low: float
    close: float
    tick_volume: float
    # Force scores
    force_eur: float
    force_usd: float
    force_gbp: float
    force_jpy: float
    force_cad: float
    force_chf: float
    force_aud: float
    force_nzd: float


@dataclass
class CalibrationResult:
    """Résultat calibration pour un signal."""
    signal: CalibrationSignal
    fatman_state: FatmanLiveState
    oracle_verdict: FatmanVerdict
    v10_level: str
    v10_confluence: float
    agreement: bool  # fatman vs oracle
    alignment_score: float  # 0-100, à quel point fatman state confirme oracle


def _get_recent_signals(
    db_path: str,
    n: int = 10,
    timeframes: Tuple[str, ...] = TIMEFRAMES,
    pairs: Tuple[str, ...] = PAIRS,
) -> List[CalibrationSignal]:
    """Charge N signaux récents (barres fermées) depuis forces_snapshots."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    tf_placeholders = ",".join("?" for _ in timeframes)
    pair_placeholders = ",".join("?" for _ in pairs)

    query = f"""
    SELECT symbol, timeframe, timestamp, bar_time, server_time,
           open, high, low, close, tick_volume,
           force_eur, force_usd, force_gbp, force_jpy,
           force_cad, force_chf, force_aud, force_nzd
    FROM forces_snapshots
    WHERE is_closed_bar=1
      AND timeframe IN ({tf_placeholders})
      AND symbol IN ({pair_placeholders})
    ORDER BY bar_time DESC
    LIMIT ?
    """
    params = list(timeframes) + list(pairs) + [n]
    rows = cur.execute(query, params).fetchall()
    con.close()

    signals = []
    for r in rows:
        signals.append(CalibrationSignal(
            symbol=r["symbol"],
            timeframe=r["timeframe"],
            timestamp=r["timestamp"],
            bar_time=r["bar_time"],
            open=r["open"],
            high=r["high"],
            low=r["low"],
            close=r["close"],
            tick_volume=r["tick_volume"] or 0.0,
            force_eur=r["force_eur"] or 50.0,
            force_usd=r["force_usd"] or 50.0,
            force_gbp=r["force_gbp"] or 50.0,
            force_jpy=r["force_jpy"] or 50.0,
            force_cad=r["force_cad"] or 50.0,
            force_chf=r["force_chf"] or 50.0,
            force_aud=r["force_aud"] or 50.0,
            force_nzd=r["force_nzd"] or 50.0,
        ))
    return signals


def _build_fatman_setup(
    signal: CalibrationSignal,
    fatman_state: FatmanLiveState,
    prior_closes: List[float],
    prior_volumes: List[float],
    atr_value: float,
) -> FatmanSetup:
    """Construit un FatmanSetup pour l'oracle à partir du signal DB + état Fatman."""
    # Direction dérivée de base_score vs quote_score
    if fatman_state.base_score > fatman_state.quote_score + 5:
        direction = "LONG"
    elif fatman_state.quote_score > fatman_state.base_score + 5:
        direction = "SHORT"
    else:
        direction = "LONG" if fatman_state.base_score >= fatman_state.quote_score else "SHORT"

    # BOS depuis momentum
    bos_map = {
        Momentum.UP: "BOS_BULL",
        Momentum.DOWN: "BOS_BEAR",
        Momentum.FLAT: "NONE",
        Momentum.UNKNOWN: "NONE",
    }
    bos = bos_map.get(fatman_state.momentum, "NONE")

    # Session depuis timestamp
    from datetime import datetime as _dt
    ts = signal.timestamp.replace("Z", "+00:00") if signal.timestamp.endswith("Z") else signal.timestamp
    dt = _dt.fromisoformat(ts)
    hour = dt.hour
    if 7 <= hour < 16:
        session = "LONDON"
    elif 13 <= hour < 22:
        session = "NY"
    elif 22 <= hour or hour < 7:
        session = "ASIAN"
    else:
        session = "OVERLAP"

    return FatmanSetup(
        setup_id=f"{signal.symbol}_{signal.timeframe}_{signal.bar_time}",
        symbol=signal.symbol,
        timestamp=signal.timestamp,
        timeframe=signal.timeframe,
        open=signal.open,
        high=signal.high,
        low=signal.low,
        close=signal.close,
        tick_volume=signal.tick_volume,
        expected_direction=direction,
        session=session,
        bos=bos,
        vsa_state="NEUTRAL",  # pas de VSA ici
        prior_closes=prior_closes,
        prior_volumes=prior_volumes,
        atr_value=atr_value,
        v10_setup_level="A1",  # placeholder, sera mis à jour
        v10_confluence_score=0.0,
    )


def _get_prior_bars(db_path: str, symbol: str, timeframe: str, limit: int = 60) -> Tuple[List[float], List[float]]:
    """Récupère les closes et volumes précédents pour EMA/ATR."""
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    rows = cur.execute(
        "SELECT close, tick_volume FROM forces_snapshots "
        "WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
        "ORDER BY bar_time DESC LIMIT ?",
        (symbol, timeframe, limit)
    ).fetchall()
    con.close()
    rows.reverse()
    closes = [float(r[0]) for r in rows]
    volumes = [float(r[1] or 0.0) for r in rows]
    return closes, volumes


def _compute_atr(db_path: str, symbol: str, timeframe: str, period: int = 14) -> float:
    """Calcule ATR(14) approximatif depuis les barres."""
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    rows = cur.execute(
        "SELECT high, low, close FROM forces_snapshots "
        "WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
        "ORDER BY bar_time DESC LIMIT ?",
        (symbol, timeframe, period + 1)
    ).fetchall()
    con.close()
    rows.reverse()
    if len(rows) < 2:
        return 0.0
    trs = []
    for i in range(1, len(rows)):
        h, l, c_prev = rows[i]
        _, _, c = rows[i-1]
        tr = max(h - l, abs(h - c), abs(l - c))
        trs.append(tr)
    if not trs:
        return 0.0
    return sum(trs[-period:]) / min(period, len(trs))


def _load_v10_signal(db_path: str, symbol: str, timeframe: str, timestamp: str) -> Tuple[str, float]:
    """Charge le niveau V10 et confluence depuis les décisions live récentes."""
    # On cherche dans v10_decisions.db
    dec_db = Path("data/v10_decisions.db")
    if not dec_db.exists():
        return "NONE", 0.0
    try:
        con = sqlite3.connect(str(dec_db))
        cur = con.cursor()
        row = cur.execute(
            "SELECT signal_level, confluence_score FROM decisions "
            "WHERE pair=? AND timeframe=? AND timestamp LIKE ? "
            "ORDER BY rowid DESC LIMIT 1",
            (symbol, timeframe, timestamp[:13] + "%")
        ).fetchone()
        con.close()
        if row:
            return row[0] or "NONE", float(row[1] or 0.0)
    except Exception:
        pass
    return "NONE", 0.0


def run_calibration(
    db_path: str = DEFAULT_DB_PATH,
    n_signals: int = 10,
    timeframes: Tuple[str, ...] = TIMEFRAMES,
    pairs: Tuple[str, ...] = PAIRS,
) -> List[CalibrationResult]:
    """Lance la calibration complète sur N signaux."""
    log.info(f"Chargement de {n_signals} signaux récents...")
    signals = _get_recent_signals(db_path, n_signals, timeframes, pairs)
    log.info(f"{len(signals)} signaux chargés")

    results = []
    for sig in signals:
        # 1. État Fatman DB Reader
        fatman_state = get_fatman_live(
            sig.symbol, sig.timeframe,
            db_path=db_path,
            max_age_seconds=300,
        )

        # 2. Prior bars pour Oracle
        prior_closes, prior_volumes = _get_prior_bars(db_path, sig.symbol, sig.timeframe, limit=60)
        atr_value = _compute_atr(db_path, sig.symbol, sig.timeframe, period=14)

        # 3. Setup pour Oracle
        setup = _build_fatman_setup(sig, fatman_state, prior_closes, prior_volumes, atr_value)

        # 4. Niveau V10 réel
        v10_level, v10_confluence = _load_v10_signal(db_path, sig.symbol, sig.timeframe, sig.timestamp)
        setup.v10_setup_level = v10_level
        setup.v10_confluence_score = v10_confluence

        # 5. Oracle Hawkeye
        oracle_verdict = oracle_fatman(setup)

        # 6. Agreement
        agreement = oracle_verdict.agreement

        # 7. Score d'alignement (corrélation base_score vs oracle score)
        # Si base_score élevé + LONG attendu = alignement
        fatman_direction = "LONG" if fatman_state.base_score > fatman_state.quote_score else "SHORT"
        oracle_direction = setup.expected_direction
        direction_agree = (fatman_direction == oracle_direction)
        
        # Score composite
        alignment = oracle_verdict.score
        if direction_agree:
            alignment += 10  # bonus
        alignment = min(100, alignment)

        results.append(CalibrationResult(
            signal=sig,
            fatman_state=fatman_state,
            oracle_verdict=oracle_verdict,
            v10_level=v10_level,
            v10_confluence=v10_confluence,
            agreement=agreement,
            alignment_score=alignment,
        ))

    return results


def print_report(results: List[CalibrationResult]) -> None:
    """Affiche le rapport de calibration."""
    print("=" * 80)
    print(" V10 FATMAN LIVE CALIBRATION — RAPPORT")
    print("=" * 80)
    print(f" Signaux analysés : {len(results)}")
    print(f" Règle Hawkeye : validation_threshold={FATMAN_HAWKEYE_RULES['validation_threshold']}, rejection={FATMAN_HAWKEYE_RULES['rejection_threshold']}")
    print()

    # Stats globales
    agreements = sum(1 for r in results if r.agreement)
    avg_alignment = sum(r.alignment_score for r in results) / len(results) if results else 0
    avg_oracle = sum(r.oracle_verdict.score for r in results) / len(results) if results else 0
    
    print(" ── STATS GLOBALES ────────────────────────────────────────────────")
    print(f"  Agreement Oracle↔V10    : {agreements}/{len(results)} ({agreements/len(results)*100:.1f}%)")
    print(f"  Score Oracle moyen      : {avg_oracle:.1f}/100")
    print(f"  Alignement moyen        : {avg_alignment:.1f}/100")
    print()

    # Détail par signal
    print(" ── DÉTAIL PAR SIGNAL ─────────────────────────────────────────────")
    print(f"  {'SYMBOL':<8} {'TF':<4} {'TIMESTAMP':<20} {'FATMAN':<8} {'ORACLE':<8} {'V10':<4} {'AGREE':<5} {'ALIGN':<5} {'DIR'}")
    for r in results:
        fm_dir = "L" if r.fatman_state.base_score > r.fatman_state.quote_score else "S"
        oracle_dir = r.oracle_verdict.reason.split("Direction attendue : ")[1].split("\n")[0][0] if "Direction attendue" in r.oracle_verdict.reason else "?"
        agree_mark = "✅" if r.agreement else "❌"
        print(f"  {r.signal.symbol:<8} {r.signal.timeframe:<4} {r.signal.timestamp[:19]:<20} "
              f"{r.fatman_state.source.value:<8} {r.oracle_verdict.verdict:<8} {r.v10_level:<4} "
              f"{agree_mark:<5} {r.alignment_score:<5.1f} {fm_dir}/{oracle_dir}")

    print()
    print(" ── BREAKDOWN ORACLE (moyennes) ───────────────────────────────────")
    # Moyenne des breakdowns
    if results:
        comps = {}
        for r in results:
            for k, v in r.oracle_verdict.breakdown.items():
                comps.setdefault(k, []).append(v)
        for k, vals in sorted(comps.items()):
            avg = sum(vals) / len(vals)
            weight = FATMAN_HAWKEYE_RULES.get(f"{k}_weight", 0)
            contrib = avg * weight * 100
            print(f"  {k:<15} : avg={avg:.3f}  weight={weight:.2f}  contrib={contrib:.1f}")

    print()
    print("=" * 80)
    verdict = "CALIBRÉ" if agreements >= len(results) * 0.7 else "RE-CALIBRATION REQUISE"
    print(f" VERDICT : {verdict}")
    print("=" * 80)


def save_json(results: List[CalibrationResult], output_path: str) -> None:
    """Sauvegarde le rapport en JSON (R9 audit)."""
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_signals": len(results),
        "hawkeye_rules": FATMAN_HAWKEYE_RULES,
        "active_sessions": list(ACTIVE_FATMAN_SESSIONS),
        "results": [
            {
                "signal": {
                    "symbol": r.signal.symbol,
                    "timeframe": r.signal.timeframe,
                    "timestamp": r.signal.timestamp,
                    "bar_time": r.signal.bar_time,
                    "ohlc": {
                        "open": r.signal.open,
                        "high": r.signal.high,
                        "low": r.signal.low,
                        "close": r.signal.close,
                    },
                    "tick_volume": r.signal.tick_volume,
                    "forces": {
                        "eur": r.signal.force_eur,
                        "usd": r.signal.force_usd,
                        "gbp": r.signal.force_gbp,
                        "jpy": r.signal.force_jpy,
                        "cad": r.signal.force_cad,
                        "chf": r.signal.force_chf,
                        "aud": r.signal.force_aud,
                        "nzd": r.signal.force_nzd,
                    },
                },
                "fatman_state": r.fatman_state.as_dict(),
                "oracle_verdict": r.oracle_verdict.as_dict(),
                "v10_level": r.v10_level,
                "v10_confluence": r.v10_confluence,
                "agreement": r.agreement,
                "alignment_score": r.alignment_score,
            }
            for r in results
        ],
        "summary": {
            "total": len(results),
            "agreements": sum(1 for r in results if r.agreement),
            "agreement_rate": sum(1 for r in results if r.agreement) / len(results) if results else 0,
            "avg_oracle_score": sum(r.oracle_verdict.score for r in results) / len(results) if results else 0,
            "avg_alignment": sum(r.alignment_score for r in results) / len(results) if results else 0,
        },
    }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"Rapport JSON sauvegardé: {output_path}")


def main() -> int:
    ap = argparse.ArgumentParser(description="V10 Fatman Live Calibration")
    ap.add_argument("--db", default=DEFAULT_DB_PATH, help="Chemin v9_forces.db")
    ap.add_argument("--n", type=int, default=10, help="Nombre de signaux à calibrer")
    ap.add_argument("--json", default="", help="Fichier JSON sortie (défaut: reports/v10_fatman_calib_<date>.json)")
    ap.add_argument("--verbose", "-v", action="store_true", help="Logs détaillés")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    db_path = Path(args.db)
    if not db_path.exists():
        log.error(f"DB introuvable: {db_path}")
        return 2

    results = run_calibration(
        db_path=str(db_path),
        n_signals=args.n,
    )

    print_report(results)

    if args.json:
        out_path = args.json
    else:
        date = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        out_path = ROOT / "reports" / f"v10_fatman_calib_{date}.json"
    save_json(results, out_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())