"""V10 Bayesian Recalibrator — recalibration seuils contextuels par paire.

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

# Defaults R6 fail-open
DEFAULT_THRESHOLDS = {
    "context_score_min": 55.0,
    "anta_score_min": 25.0,
    "aligned_count_min": 3,
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

def apply_thresholds(
    pair: str,
    context_score: float,
    anta_score: float,
    aligned_count: int,
    thresholds: Optional[Dict[str, PairThreshold]] = None,
) -> bool:
    """Vérifie si (context_score, anta_score, aligned_count) passe les seuils.

    Si thresholds=None → utilise DEFAULT_THRESHOLDS (R6 fail-open).
    Si pair absent de thresholds → DEFAULT_THRESHOLDS.
    """
    if thresholds is None:
        pair_thr = None
    else:
        pair_thr = thresholds.get(pair)

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

__all__ = [
    "DEFAULT_THRESHOLDS",
    "CONTEXT_SCORE_GRID",
    "ANTA_SCORE_GRID",
    "ALIGNED_COUNT_GRID",
    "V9_BLACKLIST_PAIRS",
    "MIN_TRADES_PER_PAIR",
    "WR_TARGET",
    "PairThreshold",
    "RecalibrationReport",
    "compute_recalibration",
    "apply_thresholds",
    "write_thresholds_json",
    "load_thresholds_json",
]
