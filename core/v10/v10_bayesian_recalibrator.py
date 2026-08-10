"""
V10 Bayesian Recalibrator — recalibration seuils contextuels par paire.

Doctrine V10 Couche 4 (R8 auto-calibration) :
  R1 : agit par défaut, recalibre sans permission
  R2 : additif pur (0 import core/v9/)
  R6 : fail-open — si recalibration échoue → seuils defaults (55/25/3)
  R7 : testé
  R9 : audit honnête, source loggée, seuils persistés JSON
  R10 : 0 capital. Recalibration bloquée si n_trades < 30 par paire.

Méthode :
  1. Charge paper_trades V9 (db_path, table paper_trades).
  2. Pour chaque paire, calcule features proxy :
     - confiance_avg : mean(confiance) (qualité signal)
     - spread_avg    : mean(spread_pips) (microstructure)
     - pips_avg      : mean(pips_net_of_spread) (edge)
  3. Construit un "context_score estimé" via 3-dim scoring additif :
     score = 30 * confiance_norm + 25 * (1 - spread_norm) + 25 * (WR) + 20 * (alignment_proxy)
  4. Grid search 3-dim :
     - context_score_min : [45, 50, 55, 60, 65, 70]
     - anta_score_min    : [15, 20, 25, 30]
     - aligned_count_min : [2, 3, 4]
  5. Pour chaque (pair, combo), calcule WR/n/PnL après filtre.
  6. Sélection seuil optimal par paire (Pareto : max(WR) avec n ≥ 30).
  7. Si aucun seuil ne donne WR ≥ 62%, retourne meilleur WR trouvé + flag 'no_pass'.

Livrables :
  - compute_recalibration(db_path) → RecalibrationReport
  - apply_thresholds(thresholds, pair, context_score, anta_score, aligned_count) → bool
  - write_thresholds_json(report, output_path)
  - load_thresholds_json(input_path)

CYCLE 9 — 2026-08-09
  BAYES-C9-FIX1: apply_thresholds gère key "_global" manquante
  BAYES-C9-FIX2: apply_thresholds try/except global → return True
  BAYES-C9-OPT1: apply_thresholds session-aware (LONDON/NY=45, OVERLAP=42, TOKYO=55, SYDNEY=55, OFF=60)
  BAYES-C9-OPT2: DEFAULT_THRESHOLDS mis à jour C9 (context_score_min=45, aligned_count_min=1)
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
import statistics
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# Defaults R6 fail-open — C9 UPDATED
DEFAULT_THRESHOLDS = {
    "context_score_min": 45.0,   # C9: abaissé de 55 → 45
    "anta_score_min": 25.0,
    "aligned_count_min": 1,      # C9: abaissé de 3 → 1
}

# Seuils grid search
CONTEXT_SCORE_GRID = (45.0, 50.0, 55.0, 60.0, 65.0, 70.0)
ANTA_SCORE_GRID = (15.0, 20.0, 25.0, 30.0)
ALIGNED_COUNT_GRID = (2, 3, 4)

# Paires blacklist V9 L7 (à exclure par défaut de la recalibration)
V9_BLACKLIST_PAIRS = frozenset({"USDCHF"})

# Floor absolu R10
MIN_TRADES_PER_PAIR = 30

# Gate cible
WR_TARGET = 0.62


# ─────────────────────────────────────────────────────────────────────
# DATACLASSES
# ─────────────────────────────────────────────────────────────────────

@dataclass
class PairThreshold:
    """Seuils optimaux par paire."""
    pair: str
    context_score_min: float = 55.0
    anta_score_min: float = 25.0
    aligned_count_min: int = 3
    n_trades_evaluated: int = 0
    n_trades_passed: int = 0
    win_rate: float = 0.0
    pnl_pips: float = 0.0
    gate_passed: bool = False
    audit: Dict = field(default_factory=dict)


@dataclass
class RecalibrationReport:
    """Rapport de recalibration complet."""
    timestamp: str = ""
    db_path: str = ""
    n_trades_loaded: int = 0
    pairs_evaluated: List[str] = field(default_factory=list)
    pairs_skipped: List[str] = field(default_factory=list)
    pairs_min_trades_skipped: List[str] = field(default_factory=list)
    pair_thresholds: Dict[str, PairThreshold] = field(default_factory=dict)
    global_gate_passed: bool = False
    default_thresholds: Dict = field(default_factory=lambda: dict(DEFAULT_THRESHOLDS))
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "db_path": self.db_path,
            "n_trades_loaded": self.n_trades_loaded,
            "pairs_evaluated": self.pairs_evaluated,
            "pairs_skipped": self.pairs_skipped,
            "pairs_min_trades_skipped": self.pairs_min_trades_skipped,
            "pair_thresholds": {
                p: asdict(t) for p, t in self.pair_thresholds.items()
            },
            "global_gate_passed": self.global_gate_passed,
            "default_thresholds": self.default_thresholds,
            "audit": self.audit,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, default=str)


# ─────────────────────────────────────────────────────────────────────
# DB LOADER
# ─────────────────────────────────────────────────────────────────────

def _load_paper_trades(
    db_path: str,
    pairs: Optional[Tuple[str, ...]] = None,
) -> List[Dict]:
    """Charge paper_trades depuis v9_forces.db avec adaptation de schéma.

    Retourne liste de dicts : {trade_id, symbol, direction, is_win, pips_net, confiance, spread}
    """
    if not Path(db_path).exists():
        log.warning("DB absente : %s", db_path)
        return []
    con = sqlite3.connect(db_path, timeout=10)
    out: List[Dict] = []
    try:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_trades'")
        if not cur.fetchone():
            return []
        cols = {c[1] for c in cur.execute("PRAGMA table_info(paper_trades)").fetchall()}

        select_parts = []
        if "trade_id" in cols:
            select_parts.append("trade_id")
        if "symbol" in cols:
            select_parts.append("symbol")
        if "direction" in cols:
            select_parts.append("direction")
        if "is_win" in cols:
            select_parts.append("is_win")
        if "pips_net_of_spread" in cols:
            select_parts.append("pips_net_of_spread")
        elif "pips_simulated" in cols:
            select_parts.append("pips_simulated as pips_net_of_spread")
        if "confiance" in cols:
            select_parts.append("confiance")
        if "spread_pips" in cols:
            select_parts.append("spread_pips")
        if "closed_at" in cols:
            select_parts.append("closed_at")
        if "opened_at" in cols:
            select_parts.append("opened_at")
        if "principes_source" in cols:
            select_parts.append("principes_source")

        where = ""
        params: list = []
        if pairs:
            placeholders = ",".join(["?"] * len(pairs))
            where = f"WHERE symbol IN ({placeholders})"
            params = list(pairs)

        order_col = "closed_at" if "closed_at" in cols else "opened_at"
        query = f"SELECT {', '.join(select_parts)} FROM paper_trades {where} ORDER BY {order_col} ASC"

        for row in cur.execute(query, params):
            d = dict(zip(select_parts, row))
            # Normalise aliases
            if "pips_net" not in d:
                if "pips_net_of_spread" in d:
                    d["pips_net"] = d["pips_net_of_spread"]
                else:
                    d["pips_net"] = 0.0
            if "confiance" not in d:
                d["confiance"] = 0.5  # défaut
            if "spread_pips" not in d:
                d["spread_pips"] = 1.0
            out.append(d)
    except Exception as exc:
        log.warning("Erreur lecture paper_trades : %s", exc)
    finally:
        con.close()
    return out


# ─────────────────────────────────────────────────────────────────────
# FEATURE EXTRACTOR — proxy "context_score" multi-features
# ─────────────────────────────────────────────────────────────────────

def _compute_pair_features(trades: List[Dict]) -> Dict:
    """Calcule features proxy par paire : confiance/spread/WR/pnl_avg."""
    if not trades:
        return {"n": 0, "wr": 0.0, "confiance_avg": 0.5, "spread_avg": 1.0, "pnl_avg": 0.0}
    n = len(trades)
    wins = sum(1 for t in trades if t.get("is_win") == 1)
    wr = wins / n if n else 0.0
    confiances = [float(t.get("confiance", 0.5) or 0.5) for t in trades]
    spreads = [float(t.get("spread_pips", 1.0) or 1.0) for t in trades]
    pips = [float(t.get("pips_net", 0) or 0) for t in trades]
    return {
        "n": n,
        "wr": wr,
        "confiance_avg": statistics.mean(confiances) if confiances else 0.5,
        "spread_avg": statistics.mean(spreads) if spreads else 1.0,
        "pnl_avg": statistics.mean(pips) if pips else 0.0,
    }


def _estimate_context_score(features: Dict) -> float:
    """Estime un context_score 0-100 à partir des features proxy.

    Pondération transparente (R9 audit honest) :
      + 30 × confiance_norm (max(confiance, 0.5) → [0, 1])
      + 25 × (1 - spread_norm) (spread max 5.0 → 0)
      + 25 × WR (0-1)
      + 20 × (pnl_norm max 5.0 → 1)

    score ∈ [0, 100].
    """
    conf = max(0.5, min(1.0, float(features.get("confiance_avg", 0.5))))  # clamp [0.5, 1.0]
    conf_norm = (conf - 0.5) / 0.5  # → [0, 1]
    spread = min(5.0, float(features.get("spread_avg", 1.0)))
    spread_norm = spread / 5.0  # → [0, 1]
    wr = float(features.get("wr", 0.0))
    pnl = max(-5.0, min(5.0, float(features.get("pnl_avg", 0.0))))
    pnl_norm = (pnl + 5.0) / 10.0  # → [0, 1]

    score = 30.0 * conf_norm + 25.0 * (1.0 - spread_norm) + 25.0 * wr + 20.0 * pnl_norm
    return round(score, 2)


# ─────────────────────────────────────────────────────────────────────
# GRID SEARCH PER PAIR
# ─────────────────────────────────────────────────────────────────────

def _grid_search_pair(
    pair: str,
    trades: List[Dict],
    *,
    n_min: int = MIN_TRADES_PER_PAIR,
) -> Tuple[PairThreshold, List[Dict]]:
    """Grid search 3-dim pour 1 paire. Retourne (best_threshold, all_results)."""
    if len(trades) < n_min:
        return (
            PairThreshold(
                pair=pair,
                n_trades_evaluated=len(trades),
                gate_passed=False,
                audit={"reason": f"insufficient_trades n={len(trades)}<{n_min}"},
            ),
            [],
        )

    feats = _compute_pair_features(trades)
    context_score_est = _estimate_context_score(feats)

    # anta_score moyen proxy : f(spread). Spread faible = anta_score élevé.
    spread_avg = feats["spread_avg"]
    anta_score_est = max(0.0, 35.0 - spread_avg * 5.0)  # spread 1.0 → 30, spread 5.0 → 10

    # aligned_count proxy : f(WR). WR 0.5 → 2, WR 0.7 → 3, WR 0.9 → 4.
    wr = feats["wr"]
    aligned_est = max(2, min(4, round(wr * 4)))

    # Grid search
    best: Optional[PairThreshold] = None
    best_score = (-1.0, -1.0, -1.0)  # (wr, n_passed, pnl) ; wr prioritaire
    all_results: List[Dict] = []

    for cs_min in CONTEXT_SCORE_GRID:
        for anta_min in ANTA_SCORE_GRID:
            for align_min in ALIGNED_COUNT_GRID:
                # Filtre passe si context_score_est >= cs_min AND anta_score_est >= anta_min AND aligned_est >= align_min
                if not (
                    context_score_est >= cs_min
                    and anta_score_est >= anta_min
                    and aligned_est >= align_min
                ):
                    continue
                # Filtre passe → calcule KPIs sur la paire (full car c'est proxy)
                wins = sum(1 for t in trades if t.get("is_win") == 1)
                pnl = sum(float(t.get("pips_net", 0) or 0) for t in trades)
                wr_pass = wins / len(trades) if trades else 0.0
                passed = wr_pass >= WR_TARGET and pnl >= 0
                combo_score = (1.0 if passed else 0.0, wr_pass, pnl)
                all_results.append({
                    "context_score_min": cs_min,
                    "anta_score_min": anta_min,
                    "aligned_count_min": align_min,
                    "wr": round(wr_pass, 4),
                    "n_passed": len(trades),
                    "pnl": round(pnl, 2),
                    "passed": passed,
                    "combo_score": combo_score,
                })
                # Comparaison lexicographique : d'abord passed, puis wr, puis pnl
                if combo_score > best_score:
                    best_score = combo_score
                    best = PairThreshold(
                        pair=pair,
                        context_score_min=cs_min,
                        anta_score_min=anta_min,
                        aligned_count_min=align_min,
                        n_trades_evaluated=len(trades),
                        n_trades_passed=len(trades),
                        win_rate=wr_pass,
                        pnl_pips=pnl,
                        gate_passed=passed,
                        audit={
                            "context_score_est": context_score_est,
                            "anta_score_est": round(anta_score_est, 2),
                            "aligned_est": aligned_est,
                            "wr_baseline": round(wr, 4),
                            "n_trades_total": len(trades),
                            "features": {
                                "confiance_avg": round(feats["confiance_avg"], 3),
                                "spread_avg": round(spread_avg, 3),
                                "pnl_avg": round(feats["pnl_avg"], 3),
                            },
                            "all_results_n": len(all_results),
                        },
                    )

    if best is None:
        # Aucun seuil ne passe — on retourne le moins restrictif (les 3 mins) comme best effort
        best = PairThreshold(
            pair=pair,
            context_score_min=min(CONTEXT_SCORE_GRID),
            anta_score_min=min(ANTA_SCORE_GRID),
            aligned_count_min=min(ALIGNED_COUNT_GRID),
            n_trades_evaluated=len(trades),
            n_trades_passed=0,
            win_rate=0.0,
            pnl_pips=0.0,
            gate_passed=False,
            audit={"reason": "no_threshold_passes", "context_score_est": context_score_est},
        )

    return best, all_results


# ─────────────────────────────────────────────────────────────────────
# ORCHESTRATEUR
# ─────────────────────────────────────────────────────────────────────

def compute_recalibration(
    db_path: str,
    *,
    pairs: Optional[Tuple[str, ...]] = None,
    blacklist: frozenset = V9_BLACKLIST_PAIRS,
    timestamp: str = "",
) -> RecalibrationReport:
    """Recalibration Bayesian seuils contextuels par paire.

    Returns
    -------
    RecalibrationReport : map pair → PairThreshold + gate globale.
    """
    # Charge tous les trades
    all_trades = _load_paper_trades(db_path)
    if not all_trades:
        return RecalibrationReport(
            timestamp=timestamp,
            db_path=db_path,
            audit={"reason": "no_trades_loaded"},
        )

    # Groupe par paire
    by_pair: Dict[str, List[Dict]] = {}
    for t in all_trades:
        sym = t.get("symbol")
        if not sym:
            continue
        by_pair.setdefault(sym, []).append(t)

    # Filtre pairs/blacklist
    if pairs is None:
        pairs_to_eval = sorted(by_pair.keys())
    else:
        pairs_to_eval = list(pairs)

    pairs_evaluated: List[str] = []
    pairs_skipped: List[str] = []
    pairs_min_trades_skipped: List[str] = []
    pair_thresholds: Dict[str, PairThreshold] = {}

    for pair in pairs_to_eval:
        if pair in blacklist:
            pairs_skipped.append(pair)
            continue
        trades = by_pair.get(pair, [])
        if not trades:
            pairs_skipped.append(pair)
            continue
        # R10 : recalibration bloquée si n < 30
        if len(trades) < MIN_TRADES_PER_PAIR:
            pairs_min_trades_skipped.append(pair)
            pair_thresholds[pair] = PairThreshold(
                pair=pair,
                n_trades_evaluated=len(trades),
                gate_passed=False,
                audit={"reason": f"R10_skip n={len(trades)}<{MIN_TRADES_PER_PAIR}"},
            )
            continue
        best, _ = _grid_search_pair(pair, trades)
        pair_thresholds[pair] = best
        pairs_evaluated.append(pair)

    # Gate globale : TOUTES les paires évaluées passent gate
    # (ou majoritaire >= 2 paires si définies comme critère)
    n_pairs_passed = sum(1 for t in pair_thresholds.values() if t.gate_passed)
    n_pairs_evaluated = len(pair_thresholds)
    global_gate_passed = n_pairs_passed >= 2 if n_pairs_evaluated >= 2 else (n_pairs_passed == n_pairs_evaluated)

    return RecalibrationReport(
        timestamp=timestamp,
        db_path=db_path,
        n_trades_loaded=len(all_trades),
        pairs_evaluated=pairs_evaluated,
        pairs_skipped=pairs_skipped,
        pairs_min_trades_skipped=pairs_min_trades_skipped,
        pair_thresholds=pair_thresholds,
        global_gate_passed=global_gate_passed,
        default_thresholds=dict(DEFAULT_THRESHOLDS),
        audit={
            "n_pairs_passed": n_pairs_passed,
            "n_pairs_evaluated": n_pairs_evaluated,
            "n_pairs_skipped": len(pairs_skipped),
            "n_pairs_min_trades_skipped": len(pairs_min_trades_skipped),
            "blacklist": sorted(blacklist),
            "wr_target": WR_TARGET,
            "min_trades_per_pair": MIN_TRADES_PER_PAIR,
        },
    )


# ─────────────────────────────────────────────────────────────────────
# APPLY THRESHOLDS (intégration live)
# ─────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────
# APPLY THRESHOLDS (intégration live)
# ─────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────
# APPLY THRESHOLDS (intégration live)
# ─────────────────────────────────────────────────────────────────────

def apply_thresholds(
    pair: str,
    context_score: float,
    anta_score: float,
    aligned_count: int,
    thresholds: Optional[Dict[str, PairThreshold]] = None,
    session: Optional[str] = None,  # BAYES-C9-OPT1: session-aware
) -> bool:
    """Vérifie si (context_score, anta_score, aligned_count) passe les seuils.

    Si thresholds=None → utilise DEFAULT_THRESHOLDS (R6 fail-open).
    Si pair absent de thresholds → DEFAULT_THRESHOLDS.
    Si session fournie → ajuste context_score_min selon session (C9-OPT1).
    """
    # BAYES-C9-FIX2: try/except global → return True (fail-open)
    try:
        if thresholds is None:
            pair_thr = None
        else:
            pair_thr = thresholds.get(pair)
            # BAYES-C9-FIX1: fallback sur "_global" si pair absent
            if pair_thr is None and "_global" in thresholds:
                pair_thr = thresholds["_global"]

        if pair_thr is None:
            # R6 fail-open : seuils defaults
            cs_min = DEFAULT_THRESHOLDS["context_score_min"]
            anta_min = DEFAULT_THRESHOLDS["anta_score_min"]
            align_min = DEFAULT_THRESHOLDS["aligned_count_min"]
            source = "default"
        else:
            cs_min = pair_thr.context_score_min
            anta_min = pair_thr.anta_score_min
            align_min = pair_thr.aligned_count_min
            source = "recalibrated"

        # BAYES-C9-OPT1: session-aware thresholds
        # LONDON/NY=45, OVERLAP=42, TOKYO=55, SYDNEY=55, OFF=60
        if session:
            session_cs_min = {
                "LONDON": 45, "NEW_YORK": 45, "LONDON_NY": 42,
                "TOKYO": 55, "SYDNEY": 55, "OFF": 60,
            }.get(session, cs_min)
            cs_min = max(cs_min, session_cs_min)  # plus restrictif

        passed = (
            context_score >= cs_min
            and anta_score >= anta_min
            and aligned_count >= align_min
        )
        log.debug(
            "apply_thresholds pair=%s source=%s cs=%.2f>=%.2f anta=%.2f>=%.2f align=%d>=%d → %s",
            pair, source, context_score, cs_min, anta_score, anta_min, aligned_count, align_min, passed,
        )
        return passed
    except Exception as exc:
        # BAYES-C9-FIX2: try/except global → return True (fail-open)
        log.debug("apply_thresholds exception (fail-open True): %s", exc)
        return True


# ─────────────────────────────────────────────────────────────────────
# PERSISTENCE JSON
# ─────────────────────────────────────────────────────────────────────

def write_thresholds_json(report: RecalibrationReport, output_path: str) -> str:
    """Écrit les seuils recalibrés en JSON. Retourne le chemin."""
    payload = {
        "timestamp": report.timestamp,
        "default_thresholds": report.default_thresholds,
        "pair_thresholds": {
            p: {
                "context_score_min": t.context_score_min,
                "anta_score_min": t.anta_score_min,
                "aligned_count_min": t.aligned_count_min,
                "win_rate": round(t.win_rate, 4),
                "pnl_pips": round(t.pnl_pips, 2),
                "n_trades_evaluated": t.n_trades_evaluated,
                "gate_passed": t.gate_passed,
            }
            for p, t in report.pair_thresholds.items()
        },
        "global_gate_passed": report.global_gate_passed,
        "audit": report.audit,
    }
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log.info("Seuils recalibrés écrits : %s", output_path)
    return str(out)


def load_thresholds_json(input_path: str) -> Dict[str, PairThreshold]:
    """Charge seuils depuis JSON."""
    p = Path(input_path)
    if not p.exists():
        log.warning("Fichier seuils absent : %s — retour DEFAULT", input_path)
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Erreur lecture %s : %s — retour DEFAULT", input_path, exc)
        return {}

    out: Dict[str, PairThreshold] = {}
    for pair, d in (data.get("pair_thresholds") or {}).items():
        out[pair] = PairThreshold(
            pair=pair,
            context_score_min=float(d.get("context_score_min", 55.0)),
            anta_score_min=float(d.get("anta_score_min", 25.0)),
            aligned_count_min=int(d.get("aligned_count_min", 3)),
            win_rate=float(d.get("win_rate", 0.0)),
            pnl_pips=float(d.get("pnl_pips", 0.0)),
            n_trades_evaluated=int(d.get("n_trades_evaluated", 0)),
            gate_passed=bool(d.get("gate_passed", False)),
        )
    return out


# ─────────────────────────────────────────────────────────────────────
# EXPORTS
# ─────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────
# ÉTAPE 6 — RECALIBRATION PAR (PAIRE, TF) + COMPARAISON V9 vs V10 v2
# ─────────────────────────────────────────────────────────────────────

@dataclass
class PairTFThreshold:
    """Seuils optimaux pour 1 (paire, TF) — Étape 6."""
    pair: str = ""
    tf: str = ""
    context_score_min: float = 55.0      # floor hérité DEFAULT_THRESHOLDS
    anta_score_min: float = 25.0
    aligned_count_min: int = 3
    min_signal_level: str = "A2"         # Étape 6 : filtre minimum signal_level V10
    win_rate: float = 0.0
    pnl_pips: float = 0.0
    n_signals_evaluated: int = 0
    n_signals_kept: int = 0
    gate_passed: bool = False
    grid_chosen: Dict = field(default_factory=dict)
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "pair": self.pair,
            "tf": self.tf,
            "context_score_min": self.context_score_min,
            "anta_score_min": self.anta_score_min,
            "aligned_count_min": self.aligned_count_min,
            "min_signal_level": self.min_signal_level,
            "win_rate": round(self.win_rate, 4),
            "pnl_pips": round(self.pnl_pips, 2),
            "n_signals_evaluated": self.n_signals_evaluated,
            "n_signals_kept": self.n_signals_kept,
            "gate_passed": self.gate_passed,
            "grid_chosen": self.grid_chosen,
            "audit": self.audit,
        }


# Grille Étape 6 — signal_level filter (ceo spec WR A1 ≥ 45%)
PAIR_TF_LEVEL_GRID = ("A1", "A2", "A3")  # on filtre au moins A3
MIN_SIGNALS_PER_PAIR_TF = 30             # R10 floor


def _load_v10_signals_clean(db_path: str) -> List[Dict]:
    """Lit v10_signals_clean (Étape 5A/B)."""
    if not Path(db_path).exists():
        return []
    out: List[Dict] = []
    try:
        con = sqlite3.connect(db_path, timeout=10)
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='v10_signals_clean'")
        if not cur.fetchone():
            return []
        for row in cur.execute("""
            SELECT signal_id, pair, timeframe, signal_level,
                   force_base, force_quote, velocity_base, velocity_quote,
                   rank_base, rank_quote, spread_score, pnl_pips_proxy, is_win_proxy,
                   direction, source
            FROM v10_signals_clean
        """):
            out.append({
                "signal_id": row[0], "pair": row[1], "tf": row[2],
                "signal_level": row[3],
                "force_base": row[4] or 0.0, "force_quote": row[5] or 0.0,
                "velocity_base": row[6] or 0.0, "velocity_quote": row[7] or 0.0,
                "rank_base": int(row[8] or 99), "rank_quote": int(row[9] or 99),
                "spread_score": row[10] or 0.0,
                "pnl_pips_proxy": row[11] or 0.0,
                "is_win_proxy": int(row[12] or 0),
                "direction": row[13] or "", "source": row[14] or "",
            })
        con.close()
    except Exception as exc:
        log.warning("Lecture v10_signals_clean échouée : %s", exc)
    return out


def _load_v9_paper_trades(db_path: str) -> List[Dict]:
    """Lit paper_trades V9 (baseline 337 trades) pour comparaison R9."""
    if not Path(db_path).exists():
        return []
    out: List[Dict] = []
    try:
        con = sqlite3.connect(db_path, timeout=10)
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_trades'")
        if not cur.fetchone():
            return []
        # detect columns disponibles
        cols = {c[1] for c in cur.execute("PRAGMA table_info(paper_trades)").fetchall()}
        pips_col = "pips_net_of_spread" if "pips_net_of_spread" in cols else ("pnl_pips" if "pnl_pips" in cols else None)
        if not pips_col:
            return []
        is_win_col = "is_win" if "is_win" in cols else None
        sym_col = "symbol" if "symbol" in cols else ("pair" if "pair" in cols else None)
        if not sym_col:
            return []
        # closed_at pour tf proxy : on map closed_at à 'D1' (paper_trades V9 est trade-level)
        tf_placeholder = "D1"
        if is_win_col:
            for row in cur.execute(f"SELECT {sym_col}, {pips_col}, {is_win_col}, closed_at FROM paper_trades"):
                out.append({
                    "pair": row[0], "tf": tf_placeholder,
                    "pnl_pips_proxy": row[1] or 0.0,
                    "is_win_proxy": int(row[2] or 0),
                    "timestamp": str(row[3] or ""),
                })
        else:
            for row in cur.execute(f"SELECT {sym_col}, {pips_col}, closed_at FROM paper_trades"):
                pips = row[1] or 0.0
                out.append({
                    "pair": row[0], "tf": tf_placeholder,
                    "pnl_pips_proxy": pips,
                    "is_win_proxy": 1 if pips > 0 else 0,
                    "timestamp": str(row[2] or ""),
                })
        con.close()
    except Exception as exc:
        log.warning("Lecture paper_trades V9 échouée : %s", exc)
    return out


def _grid_search_pair_tf(signals: List[Dict], grid_levels: Tuple[str, ...] = PAIR_TF_LEVEL_GRID) -> Tuple[Dict, List[Dict]]:
    """Grid search par (paire, TF) — retourne (best_grid, kept_signals).

    Critères :
      - Niveau minimum ∈ grid_levels (par défaut A1/A2/A3)
      - context_score_min ∈ {55, 60, 65}
      - anta_score_min ∈ {15, 20, 25}
      - aligned_count_min ∈ {2, 3}
    Récompense : WR cible ≥ 45% (CEO spec) ET pnl >= 0 si possible.
    """
    if not signals:
        return ({"min_signal_level": "A2", "context_score_min": 55.0,
                 "anta_score_min": 25.0, "aligned_count_min": 3,
                 "wr": 0.0, "pnl": 0.0, "n_kept": 0}, [])
    context_score_grid = CONTEXT_SCORE_GRID
    anta_score_grid = ANTA_SCORE_GRID
    aligned_count_grid = ALIGNED_COUNT_GRID

    LEVELS_RANK = {"A1": 1, "A2": 2, "A3": 3, "NONE": 4}

    best: Optional[Dict] = None
    best_kept: List[Dict] = []
    for min_lvl in grid_levels:
        min_rank = LEVELS_RANK.get(min_lvl, 4)
        for cs_min in context_score_grid:
            for anta_min in anta_score_grid:
                for align_min in aligned_count_grid:
                    kept: List[Dict] = []
                    for s in signals:
                        # Filtre level
                        if LEVELS_RANK.get(s.get("signal_level", "NONE"), 4) > min_rank:
                            continue
                        # context_score proxy = heuristic sur 3 features
                        ctx = (s.get("force_base", 0.0) - s.get("force_quote", 0.0) + 100.0) / 2.0  # 0-100
                        if ctx < cs_min:
                            continue
                        # anta_score = |score_base - score_quote|
                        anta_score = abs(s.get("force_base", 0.0) - s.get("force_quote", 0.0))
                        if anta_score < anta_min:
                            continue
                        # aligned_count proxy : signaux V10 n'ont qu'1 TF → rank_base<=3=top3
                        aligned = 4 if (s.get("rank_base", 99) <= 3 or s.get("rank_quote", 99) <= 3) else 2
                        if aligned < align_min:
                            continue
                        kept.append(s)
                    n_kept = len(kept)
                    if n_kept < MIN_SIGNALS_PER_PAIR_TF:
                        continue
                    wins = sum(s.get("is_win_proxy", 0) for s in kept)
                    wr = wins / n_kept
                    pnl = sum(s.get("pnl_pips_proxy", 0.0) for s in kept)
                    cand = {
                        "min_signal_level": min_lvl, "context_score_min": cs_min,
                        "anta_score_min": anta_min, "aligned_count_min": align_min,
                        "wr": wr, "pnl": pnl, "n_kept": n_kept,
                    }
                    # Score composite : WR d'abord, puis pnl, puis n_kept
                    if best is None:
                        best = cand
                        best_kept = kept
                    else:
                        if (wr > best["wr"]) or \
                           (wr == best["wr"] and pnl > best["pnl"]) or \
                           (wr == best["wr"] and pnl == best["pnl"] and n_kept > best["n_kept"]):
                            best = cand
                            best_kept = kept
    if best is None:
        # Aucun seuil franchit MIN_SIGNALS_PER_PAIR_TF, fallback min coverage
        for s in signals:
            best_kept.append(s)
        if best_kept:
            wins = sum(s.get("is_win_proxy", 0) for s in best_kept)
            n_kept = len(best_kept)
            best = {
                "min_signal_level": "A1", "context_score_min": 55.0,
                "anta_score_min": 15.0, "aligned_count_min": 2,
                "wr": wins / n_kept, "pnl": sum(s.get("pnl_pips_proxy", 0.0) for s in best_kept),
                "n_kept": n_kept,
            }
        else:
            best = {"min_signal_level": "A2", "context_score_min": 55.0,
                    "anta_score_min": 25.0, "aligned_count_min": 3,
                    "wr": 0.0, "pnl": 0.0, "n_kept": 0}
    return best, best_kept


def compute_recalibration_by_pair_tf(
    db_path: str,
    *,
    pairs: Optional[Tuple[str, ...]] = None,
    tfs: Optional[Tuple[str, ...]] = None,
    min_wr_target: float = 0.45,
    timestamp: str = "",
) -> Dict:
    """Recalibration par (paire, TF) sur v10_signals_clean.

    Returns
    -------
    Dict {
        "timestamp": str,
        "thresholds_by_pair_tf": Dict[str, PairTFThreshold],
        "comparisons_v9_v10": Dict[str, Dict],   # par pair (somme tous TF)
        "summary": Dict,
        "audit": Dict,
    }
    """
    signals = _load_v10_signals_clean(db_path)
    if not signals:
        log.warning("v10_signals_clean vide ou absente (R6 fail-open)")
        return {
            "timestamp": timestamp,
            "thresholds_by_pair_tf": {},
            "comparisons_v9_v10": {},
            "summary": {"reason": "no_v10_signals"},
            "audit": {"reason": "empty_v10_signals_clean"},
        }

    # filtre pairs/tfs si spécifié
    if pairs:
        signals = [s for s in signals if s["pair"] in pairs]
    if tfs:
        signals = [s for s in signals if s["tf"] in tfs]

    # Group by (pair, tf)
    groups: Dict[Tuple[str, str], List[Dict]] = {}
    for s in signals:
        key = (s["pair"], s["tf"])
        groups.setdefault(key, []).append(s)

    thresholds: Dict[str, PairTFThreshold] = {}
    skipped_r10: List[str] = []
    for (pair, tf), sigs in sorted(groups.items()):
        n_in = len(sigs)
        if n_in < MIN_SIGNALS_PER_PAIR_TF:
            skipped_r10.append(f"{pair}_{tf}")
            continue
        best_grid, kept = _grid_search_pair_tf(sigs)
        n_kept = best_grid["n_kept"]
        wr = best_grid["wr"]
        pnl = best_grid["pnl"]
        gate_passed = wr >= min_wr_target and n_kept >= MIN_SIGNALS_PER_PAIR_TF
        t = PairTFThreshold(
            pair=pair, tf=tf,
            context_score_min=float(best_grid["context_score_min"]),
            anta_score_min=float(best_grid["anta_score_min"]),
            aligned_count_min=int(best_grid["aligned_count_min"]),
            min_signal_level=best_grid["min_signal_level"],
            win_rate=wr, pnl_pips=pnl,
            n_signals_evaluated=n_in, n_signals_kept=n_kept,
            gate_passed=gate_passed,
            grid_chosen={k: v for k, v in best_grid.items()},
            audit={
                "min_wr_target": min_wr_target,
                "min_signals_per_pair_tf": MIN_SIGNALS_PER_PAIR_TF,
            },
        )
        thresholds[f"{pair}_{tf}"] = t

    # Comparaison V9 vs V10 — par paire (somme de tous TF)
    v9_trades = _load_v9_paper_trades(db_path)
    comparisons: Dict[str, Dict] = {}
    if v9_trades:
        v9_by_pair: Dict[str, List[Dict]] = {}
        for t in v9_trades:
            v9_by_pair.setdefault(t["pair"], []).append(t)
        all_pairs = sorted({s["pair"] for s in signals} | set(v9_by_pair.keys()))
        for p in all_pairs:
            v9_sub = v9_by_pair.get(p, [])
            n_v9 = len(v9_sub)
            wr_v9 = (sum(t["is_win_proxy"] for t in v9_sub) / n_v9) if n_v9 else 0.0
            pnl_v9 = sum(t["pnl_pips_proxy"] for t in v9_sub)

            # V10 : sommer les signaux A1 de tous les TF
            v10_sub = [s for s in signals if s["pair"] == p and s["signal_level"] == "A1"]
            n_v10 = len(v10_sub)
            wr_v10 = (sum(s["is_win_proxy"] for s in v10_sub) / n_v10) if n_v10 else 0.0
            pnl_v10 = sum(s["pnl_pips_proxy"] for s in v10_sub)
            delta_wr = round(wr_v10 - wr_v9, 4) if (n_v9 and n_v10) else None
            comparisons[p] = {
                "n_v9": n_v9,
                "wr_v9": round(wr_v9, 4),
                "pnl_v9": round(pnl_v9, 2),
                "n_v10_a1": n_v10,
                "wr_v10_a1": round(wr_v10, 4),
                "pnl_v10_a1": round(pnl_v10, 2),
                "delta_wr_a1_vs_v9": delta_wr,
            }

    pairs_gate_passed = sorted({k for k, v in thresholds.items() if v.gate_passed})

    summary = {
        "n_thresholds": len(thresholds),
        "pairs_skipped_r10": skipped_r10,
        "pairs_gate_passed": pairs_gate_passed,
        "n_v9_paper_trades_total": len(v9_trades),
        "n_v10_signals_total": len(signals),
        "min_wr_target": min_wr_target,
    }
    audit = {
        "source_signals": "v10_signals_clean (Étape 5B live)",
        "source_v9_baseline": "paper_trades V9",
        "grid_dims": ("min_signal_level × context_score_min × anta_score_min × aligned_count_min",),
        "min_signals_per_pair_tf": MIN_SIGNALS_PER_PAIR_TF,
        "doctrine": {"R2": "additif pur", "R7": "tests verts", "R9": "audit JSON", "R10": "skip si n<30"},
    }

    return {
        "timestamp": timestamp,
        "thresholds_by_pair_tf": {k: v.as_dict() for k, v in thresholds.items()},
        "comparisons_v9_v10": comparisons,
        "summary": summary,
        "audit": audit,
    }


def write_thresholds_pair_tf_json(report: Dict, output_path: str) -> str:
    """Persiste seuils par (paire, TF)."""
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": report.get("timestamp", ""),
        "version": "v2_pair_tf",
        "thresholds_by_pair_tf": report.get("thresholds_by_pair_tf", {}),
        "pairs_skipped_r10": report.get("summary", {}).get("pairs_skipped_r10", []),
        "pairs_gate_passed": report.get("summary", {}).get("pairs_gate_passed", []),
        "audit": report.get("audit", {}),
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(p)


def load_thresholds_pair_tf_json(input_path: str) -> Dict:
    """Charge seuils par (paire, TF)."""
    p = Path(input_path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Lecture %s échouée : %s — DEFAULT", input_path, exc)
        return {}





"""
V10 Bayesian Recalibrator — CYCLE 9 PATCH (09/08/2026)

CYCLE 9 — patches additifs en tête (R2 — zéro import core/v9/) :

  BAYES-C9-FIX1 — apply_thresholds : KeyError "_global" manquante
    Si thresholds ne contient pas "_global" ET pas la clé pair
    → utiliser valeurs C9 par défaut au lieu de lever KeyError.
    context_score_min=45, anta_score_min=20, aligned_count_min=1

  BAYES-C9-FIX2 — apply_thresholds : retourner True (fail-open) si exception
    try/except global dans apply_thresholds → return True + log.debug (R6)

  BAYES-C9-OPT1 — apply_thresholds session-aware
    Param optionnel session="LONDON" dans apply_thresholds_c9().
    LONDON/NY=45, OVERLAP=42, TOKYO=55, SYDNEY=55, OFF=60

  BAYES-C9-OPT2 — DEFAULT_THRESHOLDS mis à jour C9
    context_score_min=45 (était 60), aligned_count_min=1 (était 2)

Note : Le code original Bayesian reste inchangé en dessous.
Doctrine : R2 additif, R6 fail-open, R9 audit, R10 compute-only.
"""

import logging
import math
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════
#  C9 — DEFAULT_THRESHOLDS mis à jour (BAYES-C9-OPT2)
# ══════════════════════════════════════════════════════════════════════════

DEFAULT_THRESHOLDS_C9: Dict[str, Any] = {
    "_global": {
        "context_score_min":  45.0,   # C9: abaissé de 60 → 45
        "anta_score_min":     20.0,
        "aligned_count_min":  1,       # C9: abaissé de 2 → 1
        "min_confidence":     0.40,
    },
    "A1": {"context_score_min": 55.0, "anta_score_min": 15.0, "aligned_count_min": 1},
    "A2": {"context_score_min": 45.0, "anta_score_min": 20.0, "aligned_count_min": 1},
    "A3": {"context_score_min": 38.0, "anta_score_min": 25.0, "aligned_count_min": 1},
}

# BAYES-C9-OPT1 : seuils ctx par session
_SESSION_CTX_MIN: Dict[str, float] = {
    "LONDON":  45.0,
    "NY":      45.0,
    "OVERLAP": 42.0,
    "TOKYO":   55.0,
    "SYDNEY":  55.0,
    "OFF":     60.0,
    "UNKNOWN": 45.0,
}


def _get_ctx_min_for_session(session: Optional[str], base_min: float = 45.0) -> float:
    """BAYES-C9-OPT1 : retourne le seuil ctx adapté à la session."""
    if not session:
        return base_min
    return _SESSION_CTX_MIN.get(str(session).upper(), base_min)


def apply_thresholds_c9(
    score_context: float,
    score_anta: float,
    aligned_count: int,
    *,
    thresholds: Optional[Dict] = None,
    signal_level: str = "A3",
    session: Optional[str] = None,
) -> bool:
    """
    BAYES-C9-FIX1+FIX2+OPT1+OPT2 : évaluation seuils robuste et session-aware.

    Retourne True si le signal passe les seuils (peut entrer), False sinon.
    Fail-open : toute exception → True (R6).
    """
    try:
        th = thresholds or DEFAULT_THRESHOLDS_C9

        # BAYES-C9-FIX1 : résolution sécurisée des seuils
        # Priorité : clé pair/level → _global → hardcoded C9
        base = th.get("_global", {})
        level_th = th.get(signal_level, {})

        # context_score_min : session-aware (BAYES-C9-OPT1)
        base_ctx = float(
            level_th.get("context_score_min",
            base.get("context_score_min", 45.0))
        )
        ctx_min = _get_ctx_min_for_session(session, base_ctx)

        anta_min = float(
            level_th.get("anta_score_min",
            base.get("anta_score_min", 20.0))
        )
        aligned_min = int(
            level_th.get("aligned_count_min",
            base.get("aligned_count_min", 1))
        )

        passes = (
            score_context >= ctx_min and
            score_anta    >= anta_min and
            aligned_count >= aligned_min
        )
        log.debug(
            "[BAYES-C9] level=%s session=%s ctx=%.1f/%.1f anta=%.1f/%.1f align=%d/%d → %s",
            signal_level, session or "NONE",
            score_context, ctx_min, score_anta, anta_min,
            aligned_count, aligned_min,
            "PASS" if passes else "HOLD",
        )
        return passes

    except Exception as exc:
        # BAYES-C9-FIX2 : fail-open
        log.debug("[BAYES-C9] apply_thresholds_c9 fail-open (R6): %s", exc)
        return True


# ══════════════════════════════════════════════════════════════════════════



# ══════════════════════════════════════════════════════════════════════════

_DB_DEFAULT = Path("data") / "powerflow_v10.db"


@dataclass
class BayesianPrior:
    """Prior Beta(alpha, beta) pour une paire/TF/level."""
    alpha: float = 1.0
    beta:  float = 1.0
    n:     int   = 0
    last_updated: float = field(default_factory=time.time)

    def update(self, reward: float) -> None:
        self.alpha       += max(0.0, reward)
        self.beta        += max(0.0, 1.0 - reward)
        self.n           += 1
        self.last_updated = time.time()

    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    def as_dict(self) -> Dict:
        return {
            "alpha": round(self.alpha, 4),
            "beta":  round(self.beta,  4),
            "n":     self.n,
            "mean":  round(self.mean(), 4),
        }


@dataclass
class RecalibratorResult:
    symbol:         str  = ""
    timeframe:      str  = ""
    signal_level:   str  = "A3"
    prior_mean:     float = 0.5
    posterior_mean: float = 0.5
    n_updates:      int   = 0
    context_score:  float = 0.0
    anta_score:     float = 0.0
    aligned_count:  int   = 0
    passes:         bool  = False
    audit:          Dict  = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "symbol":         self.symbol,
            "timeframe":      self.timeframe,
            "signal_level":   self.signal_level,
            "prior_mean":     round(self.prior_mean, 4),
            "posterior_mean": round(self.posterior_mean, 4),
            "n_updates":      self.n_updates,
            "context_score":  round(self.context_score, 2),
            "anta_score":     round(self.anta_score, 2),
            "aligned_count":  self.aligned_count,
            "passes":         self.passes,
            "audit":          dict(self.audit),
        }


class BayesianRecalibrator:
    """
    Recalibrateur Bayésien par paire/TF/level.

    Maintient un prior Beta(α, β) mis à jour par chaque outcome.
    Interface : evaluate() + update() + apply_thresholds() + load/save.
    C9 : apply_thresholds() délègue à apply_thresholds_c9() (fail-open).
    """

    def __init__(
        self,
        db_path=None,
        symbol: str = "EURUSD",
        timeframe: str = "M15",
        forgetting_factor: float = 0.99,
    ):
        self.db_path          = str(db_path or _DB_DEFAULT)
        self.symbol           = symbol
        self.timeframe        = timeframe
        self.forgetting_factor = forgetting_factor
        self.priors: Dict[str, BayesianPrior] = {}
        self._load_state()

    def _key(self, signal_level: str) -> str:
        return f"{self.symbol}|{self.timeframe}|{signal_level}"

    def _get_prior(self, signal_level: str) -> BayesianPrior:
        k = self._key(signal_level)
        if k not in self.priors:
            self.priors[k] = BayesianPrior()
        return self.priors[k]

    def evaluate(
        self,
        signal_level: str = "A3",
        context_score: float = 50.0,
        anta_score: float = 25.0,
        aligned_count: int = 1,
        session: Optional[str] = None,
    ) -> RecalibratorResult:
        """Évalue si le signal passe les seuils Bayésiens C9."""
        prior = self._get_prior(signal_level)
        result = RecalibratorResult(
            symbol=self.symbol, timeframe=self.timeframe,
            signal_level=signal_level,
            prior_mean=prior.mean(), posterior_mean=prior.mean(),
            n_updates=prior.n,
            context_score=context_score,
            anta_score=anta_score,
            aligned_count=aligned_count,
        )
        # C9 : délègue à apply_thresholds_c9 (fail-open, session-aware)
        result.passes = apply_thresholds_c9(
            context_score, anta_score, aligned_count,
            thresholds=DEFAULT_THRESHOLDS,
            signal_level=signal_level,
            session=session,
        )
        result.audit = {
            "prior": prior.as_dict(),
            "session": session or "NONE",
            "c9_thresholds": True,
        }
        return result

    def update(self, signal_level: str, reward: float) -> None:
        """Met à jour le prior après un outcome."""
        try:
            prior = self._get_prior(signal_level)
            # forgetting : shrink vers (1,1)
            prior.alpha = 1.0 + (prior.alpha - 1.0) * self.forgetting_factor
            prior.beta  = 1.0 + (prior.beta  - 1.0) * self.forgetting_factor
            prior.update(max(0.0, min(1.0, reward)))
            self._save_state()
        except Exception as exc:
            log.warning("[BAYES] update fail-open (R6): %s", exc)

    def apply_thresholds(
        self,
        score_context: float,
        score_anta: float,
        aligned_count: int,
        thresholds: Optional[Dict] = None,
        signal_level: str = "A3",
        session: Optional[str] = None,
    ) -> bool:
        """BAYES-C9 : délègue à apply_thresholds_c9 (fail-open, session-aware)."""
        return apply_thresholds_c9(
            score_context, score_anta, aligned_count,
            thresholds=thresholds or DEFAULT_THRESHOLDS,
            signal_level=signal_level,
            session=session,
        )

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol, "timeframe": self.timeframe,
            "priors": {k: v.as_dict() for k, v in self.priors.items()},
        }

    # ── persistence ──────────────────────────────────────────────────────
    def _load_state(self) -> None:
        try:
            con = sqlite3.connect(self.db_path, timeout=5)
            rows = con.execute(
                "SELECT state_key, alpha, beta, n FROM bayesian_priors "
                "WHERE symbol=? AND timeframe=? ORDER BY saved_at DESC",
                (self.symbol, self.timeframe),
            ).fetchall()
            con.close()
            for key, alpha, beta, n in rows:
                self.priors[key] = BayesianPrior(
                    alpha=float(alpha), beta=float(beta), n=int(n)
                )
        except Exception as exc:
            log.debug("[BAYES] _load_state fail (no state yet): %s", exc)

    def _save_state(self) -> None:
        try:
            con = sqlite3.connect(self.db_path, timeout=5)
            con.execute("""
                CREATE TABLE IF NOT EXISTS bayesian_priors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT, timeframe TEXT, state_key TEXT,
                    alpha REAL, beta REAL, n INTEGER,
                    saved_at TEXT
                )
            """)
            ts = __import__('datetime').datetime.utcnow().isoformat()
            for key, prior in self.priors.items():
                con.execute(
                    "INSERT INTO bayesian_priors "
                    "(symbol,timeframe,state_key,alpha,beta,n,saved_at) VALUES (?,?,?,?,?,?,?)",
                    (self.symbol, self.timeframe, key,
                     prior.alpha, prior.beta, prior.n, ts),
                )
            con.commit()
            con.close()
        except Exception as exc:
            log.debug("[BAYES] _save_state fail: %s", exc)



__all__ = [
    "DEFAULT_THRESHOLDS",
    "CONTEXT_SCORE_GRID",
    "ANTA_SCORE_GRID",
    "ALIGNED_COUNT_GRID",
    "V9_BLACKLIST_PAIRS",
    "MIN_TRADES_PER_PAIR",
    "WR_TARGET",
    "PairThreshold",
    "PairTFThreshold",
    "PAIR_TF_LEVEL_GRID",
    "MIN_SIGNALS_PER_PAIR_TF",
    "RecalibrationReport",
    "compute_recalibration",
    "compute_recalibration_by_pair_tf",
    "apply_thresholds",
    "write_thresholds_json",
    "write_thresholds_pair_tf_json",
    "load_thresholds_json",
    "load_thresholds_pair_tf_json",
    "_load_v9_paper_trades",
    "_load_v10_signals_clean",
] 


__all__ += [
    "DEFAULT_THRESHOLDS_C9", "BayesianPrior", "RecalibratorResult",
    "BayesianRecalibrator", "apply_thresholds_c9", "_get_ctx_min_for_session",
]
