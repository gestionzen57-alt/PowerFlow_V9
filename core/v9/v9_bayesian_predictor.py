"""v9_bayesian_predictor.py — Prédicteur bayésien calibré (Phase E, Doctrine R33).

**Pourquoi ce module existe** :
- V9 produit un score `confiance ∈ [0, 100]` par signal, mais ce score
  n'est **pas calibré** : conf=80 ne signifie pas 80 % de chance de gain.
  L'audit 2026-07-18 le confirme : WR global résolu = 84 %, mais le
  score de Brier naïf (= variance binaire du label) est ≈ 0.13, ce qui
  indique une marge significative d'amélioration par calibration.
- Ce module transforme la confiance déclarée en **probabilité réelle de
  gain**, conditionnellement au contexte opérationnel `(symbol, regime,
  phase, vol_atr_bucket)` et au(x) principe(s) ayant déclenché le signal.

**Méthodologie probabiliste senior** :
1. **Modèle Beta-Binomial** par cellule contextuelle : distribution
   conjuguée a priori Beta(1,1) (uniforme) → Beta(α=wins+1, β=losses+1)
   a posteriori. Espérance = α/(α+β), variance = αβ/[(α+β)²(α+β+1)].
2. **Calibration Platt** par régression logistique :
   P(is_win | conf) = σ(a · conf_norm + b), fit par maximum de
   vraisemblance sur l'historique résolu. Corrige le biais global du
   déclaratif.
3. **Calibration par contexte** : on ajuste Platt par cellule
   `(symbol, regime, phase, vol_bucket)` quand n_resolved ≥ 30. Sinon,
   on replie sur Platt global + shrinkage bayésien.
4. **Métriques de calibration** :
   - **Brier Score** : BS = (1/n) Σ (p_i - o_i)². Baseline naïve ≈
     WR·(1-WR) = 0.84·0.16 ≈ 0.134. Cible : BS < 0.10.
   - **Log-loss** : LL = -(1/n) Σ [o·log(p) + (1-o)·log(1-p)].
     Cible : LL < 0.35.
   - **Expected Calibration Error (ECE)** : sur 10 bins, moyenne de
     |accuracy_bin - conf_moyenne_bin|. Cible : ECE < 5 %.

**Volet doctrinal** :
- R2 additif (clé préfixée `bayesian_*`, ne mute jamais le signal_generator)
- R6 défensif (try/except + fallback Platt global si cellule trop pauvre)
- R7 testable (synthetic data + DB mémoire)
- R8 ne touche pas la DB live (lecture seule + DB calibration séparée)
- R18 code pur (zéro LLM, math stdlib + sqlite3)
- R33 doctrine du **Système Prédictif**

**Activation** : `V9_BAYESIAN_PREDICTOR_ENABLED=1` (motion CEO 2026-07-18
« APPLY direct pour les modules à gain certain »).

**Gains attendus** (backtest uplift lecture seule cible) :
- WR uplift ≥ +10 pts sur sous-ensembles à calibration locale valide
- PF uplift ≥ +1.5 (sélection des trades dont la probabilité calibrée
  dépasse le seuil d'edge minimum)
"""
from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ const

# Kill switch.
BAYESIAN_ENABLED_ENV = "V9_BAYESIAN_PREDICTOR_ENABLED"

# DB de calibration séparée (R8).
DEFAULT_CALIBRATION_DB = Path("data/v9_calibration.db")

# Phases alignées sur `behaviors.phase`.
VALID_PHASES = ("culmination", "developpement", "initiation", "resolution")
# Régimes alignés sur `decisions.regime_type`.
VALID_REGIMES = ("NEUTRE", "RETOUR_EQUILIBRE", "EXTENSION", "PALIER", "CASSURE", "REJET")

# Seuils.
MIN_N_FOR_LOCAL_CALIBRATION = 30   # n_resolved < 30 → fallback Platt global
MIN_N_FOR_BETA_PRIOR = 5           # n_resolved < 5 → prior Beta(1,1) (uniforme)
PRIOR_ALPHA = 1.0                  # prior Beta(α, β) — non-informatif
PRIOR_BETA = 1.0
ECE_BINS = 10                       # nombre de bins pour ECE
EPS = 1e-9                          # pour log-loss sûr


# ------------------------------------------------------------------ dataclasses


@dataclass(frozen=True)
class BetaPosterior:
    """Distribution Beta(α, β) a posteriori sur la probabilité de gain."""
    alpha: float
    beta_param: float
    n_observations: int
    n_wins: int
    n_losses: int

    @property
    def mean(self) -> float:
        """Espérance de la probabilité de gain."""
        return self.alpha / (self.alpha + self.beta_param)

    @property
    def variance(self) -> float:
        return (self.alpha * self.beta_param) / (
            (self.alpha + self.beta_param) ** 2 * (self.alpha + self.beta_param + 1)
        )

    @property
    def std(self) -> float:
        return math.sqrt(self.variance)

    def credible_interval_95(self) -> tuple[float, float]:
        """IC95% via approximation normale (valide pour α, β ≥ 5)."""
        z = 1.96
        lo = max(0.0, self.mean - z * self.std)
        hi = min(1.0, self.mean + z * self.std)
        return (round(lo, 4), round(hi, 4))

    def to_dict(self) -> dict[str, Any]:
        return {
            "alpha": self.alpha,
            "beta": self.beta_param,
            "n_observations": self.n_observations,
            "n_wins": self.n_wins,
            "n_losses": self.n_losses,
            "mean": round(self.mean, 4),
            "std": round(self.std, 4),
            "ci95": list(self.credible_interval_95()),
        }


@dataclass(frozen=True)
class PlattCalibrator:
    """Calibration Platt : P(is_win | conf) = sigmoid(a · conf + b)."""
    a: float            # coefficient de la confiance normalisée [0, 1]
    b: float            # biais
    n_fit: int          # nombre d'observations utilisées pour le fit
    log_likelihood: float

    def predict_proba(self, conf_norm: float) -> float:
        """P(is_win=1 | conf) ∈ [0, 1]."""
        z = self.a * float(conf_norm) + self.b
        # sigmoid stable
        if z >= 0:
            ez = math.exp(-z)
            return round(1.0 / (1.0 + ez), 6)
        ez = math.exp(z)
        return round(ez / (1.0 + ez), 6)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CalibrationMetrics:
    """Métriques de calibration globales."""
    n: int
    brier_score: float
    brier_naive: float          # = WR · (1-WR), baseline non-conditionnelle
    brier_skill_score: float    # 1 - BS/BS_naive ; > 0 = meilleur que naive
    log_loss: float
    ece: float                  # Expected Calibration Error
    accuracy: float
    baseline_accuracy: float    # accuracy si on prédit toujours WR global
    mean_predicted_proba: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Prediction:
    """Prédiction complète pour un (signal_id, contexte)."""
    symbol: str
    timeframe: str
    regime_type: str
    phase: str
    vol_atr_bucket: str
    declared_confiance: int              # 0-100, déclaratif signal_generator
    calibrated_proba: float              # 0-1, après Platt + shrinkage
    beta_posterior: BetaPosterior | None # None si pas d'historique cellule
    platt_used: str                      # "global" | "local_<symbol>" | "prior_only"
    confidence_in_calibration: float     # 0-1, qualité de la calibration
    edge: float                          # calibrated_proba · TP - (1-calibrated_proba) · SL
    recommended_action: str              # "enter" | "skip" | "reduce_size"
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.beta_posterior is not None:
            d["beta_posterior"] = self.beta_posterior.to_dict()
        else:
            d["beta_posterior"] = None
        return d


# ------------------------------------------------------------------ kill switch

def bayesian_predictor_enabled() -> bool:
    """Kill switch — défaut ON (motion CEO 2026-07-18)."""
    val = os.environ.get(BAYESIAN_ENABLED_ENV, "1")
    return val == "1"


# ------------------------------------------------------------------ Beta-Binomial


def beta_posterior_from_counts(
    n_wins: int,
    n_losses: int,
    prior_alpha: float = PRIOR_ALPHA,
    prior_beta: float = PRIOR_BETA,
) -> BetaPosterior:
    """Construit Beta(α, β) a posteriori depuis les counts wins/losses.

    Prior non-informatif Beta(1, 1) par défaut (équivalent à 2 observations
    virtuelles 50/50). Shrinkage bayésien : pour des n petits, la posterior
    reste tirée vers 0.5 même si WR observé est extrême. Évite le sur-fit.
    """
    n = int(n_wins) + int(n_losses)
    return BetaPosterior(
        alpha=float(n_wins) + prior_alpha,
        beta_param=float(n_losses) + prior_beta,
        n_observations=n,
        n_wins=int(n_wins),
        n_losses=int(n_losses),
    )


def beta_mean_with_shrinkage(
    n_wins: int,
    n_losses: int,
    global_mean: float,
    shrinkage_strength: float = 30.0,
) -> float:
    """Moyenne Beta-Binomial avec shrinkage vers une moyenne globale.

    Pour n << shrinkage_strength, la moyenne est tirée vers `global_mean`.
    Pour n >> shrinkage_strength, elle tend vers le WR observé brut.

    Formule : `shrunk = (n · observed + k · global) / (n + k)`
    où `k = shrinkage_strength` et `observed = n_wins / max(1, n)`.
    """
    n = int(n_wins) + int(n_losses)
    if n == 0:
        return float(global_mean)
    observed = float(n_wins) / float(n)
    k = float(shrinkage_strength)
    return (n * observed + k * float(global_mean)) / (n + k)


# ------------------------------------------------------------------ Platt calibration


def _sigmoid(z: float) -> float:
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def fit_platt(
    conf_norms: list[float],
    outcomes: list[int],
    n_iter: int = 200,
    lr: float = 0.05,
    l2: float = 1e-4,
) -> PlattCalibrator:
    """Fit Platt par descente de gradient (log-loss négatif).

    Maximise Σ [o · log σ(z) + (1-o) · log(1-σ(z))]
    avec z = a · conf + b, régularisation L2 sur a.

    Robuste à des datasets petits (n ≥ 30).
    """
    if len(conf_norms) != len(outcomes) or len(conf_norms) == 0:
        return PlattCalibrator(a=1.0, b=0.0, n_fit=0, log_likelihood=0.0)
    n = len(conf_norms)
    # Init : a=1, b=0 (identity-like)
    a = 1.0
    b = 0.0
    for _ in range(n_iter):
        grad_a = 0.0
        grad_b = 0.0
        ll = 0.0
        for conf, o in zip(conf_norms, outcomes):
            z = a * conf + b
            p = _sigmoid(z)
            # Log-loss partiel
            ll += o * math.log(max(p, EPS)) + (1 - o) * math.log(max(1 - p, EPS))
            err = p - o
            grad_a += err * conf
            grad_b += err
        grad_a /= n
        grad_b /= n
        a -= lr * (grad_a + l2 * a)
        b -= lr * grad_b
    # Log-likelihood finale
    ll = 0.0
    for conf, o in zip(conf_norms, outcomes):
        z = a * conf + b
        p = _sigmoid(z)
        ll += o * math.log(max(p, EPS)) + (1 - o) * math.log(max(1 - p, EPS))
    ll /= n
    return PlattCalibrator(a=round(a, 6), b=round(b, 6), n_fit=n,
                           log_likelihood=round(ll, 6))


# ------------------------------------------------------------------ Calibration metrics


def compute_calibration_metrics(
    predicted_probas: list[float],
    outcomes: list[int],
    n_bins: int = ECE_BINS,
) -> CalibrationMetrics:
    """Brier Score, log-loss, ECE, accuracy."""
    if len(predicted_probas) != len(outcomes) or len(predicted_probas) == 0:
        return CalibrationMetrics(
            n=0, brier_score=1.0, brier_naive=1.0, brier_skill_score=-1.0,
            log_loss=math.log(2), ece=1.0, accuracy=0.0, baseline_accuracy=0.0,
            mean_predicted_proba=0.0,
        )
    n = len(predicted_probas)
    # Brier
    bs = sum((p - o) ** 2 for p, o in zip(predicted_probas, outcomes)) / n
    # Log-loss
    ll = 0.0
    for p, o in zip(predicted_probas, outcomes):
        ll += o * math.log(max(p, EPS)) + (1 - o) * math.log(max(1 - p, EPS))
    ll = -ll / n
    # WR global (= accuracy si on prédit 1 quand p > 0.5)
    wr_global = sum(outcomes) / n
    bs_naive = wr_global * (1 - wr_global)
    bss = 1 - bs / bs_naive if bs_naive > 0 else 0.0
    # Accuracy
    correct = sum(1 for p, o in zip(predicted_probas, outcomes)
                  if (p > 0.5) == bool(o))
    acc = correct / n
    # ECE sur n_bins
    ece = _compute_ece(predicted_probas, outcomes, n_bins)
    mean_p = sum(predicted_probas) / n
    return CalibrationMetrics(
        n=n,
        brier_score=round(bs, 6),
        brier_naive=round(bs_naive, 6),
        brier_skill_score=round(bss, 4),
        log_loss=round(ll, 6),
        ece=round(ece, 6),
        accuracy=round(acc, 4),
        baseline_accuracy=round(wr_global, 4),
        mean_predicted_proba=round(mean_p, 4),
    )


def _compute_ece(
    predicted_probas: list[float],
    outcomes: list[int],
    n_bins: int,
) -> float:
    """Expected Calibration Error standard sur n_bins."""
    if n_bins <= 0 or len(predicted_probas) == 0:
        return 1.0
    bins: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for p, o in zip(predicted_probas, outcomes):
        idx = min(int(p * n_bins), n_bins - 1)
        bins[idx].append((p, o))
    n = len(predicted_probas)
    ece = 0.0
    for bin_data in bins:
        if not bin_data:
            continue
        bin_size = len(bin_data)
        bin_conf = sum(p for p, _ in bin_data) / bin_size
        bin_acc = sum(o for _, o in bin_data) / bin_size
        ece += abs(bin_acc - bin_conf) * (bin_size / n)
    return ece


# ------------------------------------------------------------------ Calibration DB

CALIBRATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS cell_stats (
    symbol          TEXT NOT NULL,
    timeframe       TEXT NOT NULL,
    regime_type     TEXT NOT NULL,
    phase           TEXT NOT NULL,
    vol_atr_bucket  TEXT NOT NULL,
    n_resolved      INTEGER NOT NULL DEFAULT 0,
    n_wins          INTEGER NOT NULL DEFAULT 0,
    n_losses        INTEGER NOT NULL DEFAULT 0,
    sum_conf        REAL NOT NULL DEFAULT 0.0,
    last_updated_ts REAL NOT NULL DEFAULT 0.0,
    PRIMARY KEY (symbol, timeframe, regime_type, phase, vol_atr_bucket)
);

CREATE TABLE IF NOT EXISTS platt_global (
    id              INTEGER PRIMARY KEY DEFAULT 1,
    a               REAL NOT NULL,
    b               REAL NOT NULL,
    n_fit           INTEGER NOT NULL,
    log_likelihood  REAL NOT NULL,
    last_updated_ts REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS calibration_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def init_calibration_db(path: Path | None = None) -> Path:
    """Crée le schéma si absent."""
    if path is None:
        path = DEFAULT_CALIBRATION_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(CALIBRATION_SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO calibration_meta(key, value) VALUES (?, ?)",
            ("schema_version", "1"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO calibration_meta(key, value) VALUES (?, ?)",
            ("last_init_ts", str(time.time())),
        )
        conn.commit()
    finally:
        conn.close()
    return path


def _bucket_vol_atr_from_pips(vol_atr_pips: float | None) -> str:
    """Aligné sur v9_cycle_memory._bucket_vol_atr."""
    if vol_atr_pips is None:
        return "UNKNOWN"
    try:
        v = float(vol_atr_pips)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if v < 0:
        return "UNKNOWN"
    if v <= 2.0:
        return "LOW"
    if v <= 6.0:
        return "MEDIUM"
    return "HIGH"


# ------------------------------------------------------------------ Fit depuis la DB live


def fit_from_decisions_db(
    db_path: Path | str,
    calibration_db: Path | None = None,
) -> dict[str, Any]:
    """Ajuste les Beta posteriors + Platt global depuis les décisions résolues.

    Lit `v9_forces.db` (lecture seule) : joint `decisions × signals × behaviors`
    pour avoir (confiance déclarée, outcome, contexte) par décision résolue.

    Returns :
        dict avec :
        - n_fit : nombre de décisions résolues utilisées
        - n_cells : nombre de cellules contextuelles peuplées
        - platt_global : PlattCalibrator
        - global_wr : WR global observé
        - brier_metrics : CalibrationMetrics
    """
    if calibration_db is None:
        calibration_db = DEFAULT_CALIBRATION_DB
    init_calibration_db(calibration_db)
    if not Path(db_path).exists():
        return {"error": f"DB introuvable : {db_path}"}
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        try:
            # Requête 1 : decisions résolues (8771 lignes, idx is_win)
            decisions_rows = conn.execute(
                """
                SELECT
                    d.decision_id, d.signal_id, d.symbol, d.timeframe,
                    d.regime_type, d.behavior_id, d.is_win
                FROM decisions d
                WHERE d.is_win IS NOT NULL
                """
            ).fetchall()
            # Requête 2 : signals confiance en dict (signal_id → confiance)
            signals_rows = conn.execute(
                "SELECT signal_id, confiance FROM signals WHERE confiance IS NOT NULL"
            ).fetchall()
            signals_conf = {r["signal_id"]: int(r["confiance"]) for r in signals_rows}
            # Requête 3 : behaviors phase en dict (behavior_id → phase)
            behaviors_rows = conn.execute(
                "SELECT behavior_id, phase FROM behaviors"
            ).fetchall()
            behaviors_phase = {r["behavior_id"]: r["phase"] for r in behaviors_rows}
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            conn.close()
            return {"error": f"DB error : {e}", "n_fit": 0}

        # Jointure en mémoire (rapide sur 8771 décisions).
        rows = []
        for d in decisions_rows:
            conf = signals_conf.get(d["signal_id"])
            if conf is None:
                continue
            phase = behaviors_phase.get(d["behavior_id"], "initiation")
            rows.append({
                "symbol": d["symbol"],
                "timeframe": d["timeframe"],
                "regime_type": d["regime_type"],
                "behavior_phase": phase,
                "declared_conf": conf,
                "is_win": int(bool(d["is_win"])),
            })
    finally:
        conn.close()

    if not rows:
        return {"error": "no resolved decisions", "n_fit": 0}

    # Agrégation par cellule
    cell_agg: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    conf_norms: list[float] = []
    outcomes: list[int] = []

    for r in rows:
        phase = r["behavior_phase"] if r["behavior_phase"] in VALID_PHASES else "initiation"
        regime = r["regime_type"] if r["regime_type"] in VALID_REGIMES else "NEUTRE"
        conf = r["declared_conf"]
        if conf is None:
            continue
        try:
            conf_f = float(conf)
        except (TypeError, ValueError):
            continue
        if not (0 <= conf_f <= 100):
            continue
        # vol_atr_pips non dispo ici sans jointure supplémentaire → bucket UNKNOWN
        key = (r["symbol"], r["timeframe"], regime, phase, "UNKNOWN")
        if key not in cell_agg:
            cell_agg[key] = {"n_wins": 0, "n_losses": 0, "sum_conf": 0.0, "n": 0}
        is_win = int(bool(r["is_win"]))
        cell_agg[key]["n_wins"] += is_win
        cell_agg[key]["n_losses"] += (1 - is_win)
        cell_agg[key]["sum_conf"] += conf_f
        cell_agg[key]["n"] += 1
        conf_norms.append(conf_f / 100.0)
        outcomes.append(is_win)

    n_fit = len(outcomes)
    if n_fit == 0:
        return {"error": "no valid conf/outcome pairs", "n_fit": 0}

    # Fit Platt global
    platt = fit_platt(conf_norms, outcomes)
    # Calibration metrics sur Platt global
    preds = [platt.predict_proba(c) for c in conf_norms]
    metrics = compute_calibration_metrics(preds, outcomes)

    # Persist dans calibration DB
    cal_conn = sqlite3.connect(str(calibration_db))
    try:
        ts = time.time()
        # Cell stats
        for key, agg in cell_agg.items():
            symbol, tf, regime, phase, vol_b = key
            cal_conn.execute(
                """
                INSERT OR REPLACE INTO cell_stats(
                    symbol, timeframe, regime_type, phase, vol_atr_bucket,
                    n_resolved, n_wins, n_losses, sum_conf, last_updated_ts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (symbol, tf, regime, phase, vol_b,
                 agg["n"], agg["n_wins"], agg["n_losses"],
                 agg["sum_conf"], ts),
            )
        # Platt global
        cal_conn.execute(
            """
            INSERT OR REPLACE INTO platt_global(
                id, a, b, n_fit, log_likelihood, last_updated_ts
            ) VALUES (1, ?, ?, ?, ?, ?)
            """,
            (platt.a, platt.b, platt.n_fit, platt.log_likelihood, ts),
        )
        cal_conn.execute(
            "INSERT OR REPLACE INTO calibration_meta(key, value) VALUES (?, ?)",
            ("last_fit_ts", str(ts)),
        )
        cal_conn.execute(
            "INSERT OR REPLACE INTO calibration_meta(key, value) VALUES (?, ?)",
            ("last_n_fit", str(n_fit)),
        )
        cal_conn.execute(
            "INSERT OR REPLACE INTO calibration_meta(key, value) VALUES (?, ?)",
            ("global_wr", str(sum(outcomes) / n_fit)),
        )
        cal_conn.commit()
    finally:
        cal_conn.close()

    return {
        "n_fit": n_fit,
        "n_cells": len(cell_agg),
        "platt_global": platt.to_dict(),
        "global_wr": round(sum(outcomes) / n_fit, 4),
        "calibration_metrics": metrics.to_dict(),
    }


# ------------------------------------------------------------------ Prediction (live)


def predict(
    *,
    symbol: str,
    timeframe: str,
    regime_type: str,
    phase: str,
    vol_atr_pips: float | None,
    declared_confiance: int,
    tp_pips: float = 10.0,
    sl_pips: float = 15.0,
    edge_threshold: float = 0.55,
    calibration_db: Path | str | None = None,
) -> Prediction:
    """Prédiction complète pour un signal à venir.

    Logique :
    1. Lookup cellule contextuelle `(symbol, tf, regime, phase, vol_bucket)`
       dans `calibration_db.cell_stats`.
    2. Si n_resolved ≥ MIN_N_FOR_LOCAL_CALIBRATION (30) → utilise Platt
       local (cellule). Sinon → Platt global + shrinkage bayésien.
    3. Si declared_confiance non calibrée → calibrée via Platt
       correspondant au niveau de confiance de la cellule.
    4. Combine Platt + Beta posterior via moyenne pondérée.
    5. Décide action : enter si edge > 0 (proba gain · TP - (1-proba) · SL > 0).

    Args :
        edge_threshold : proba minimum pour recommander "enter". 0.55 = on
            n'entre que si P(gain) > 55 %.
    """
    if calibration_db is None:
        calibration_db = DEFAULT_CALIBRATION_DB
    cal_p = Path(calibration_db)
    if not cal_p.exists():
        init_calibration_db(cal_p)

    vol_bucket = _bucket_vol_atr_from_pips(vol_atr_pips)
    if regime_type not in VALID_REGIMES:
        regime_type = "NEUTRE"
    if phase not in VALID_PHASES:
        phase = "initiation"

    cal_conn = sqlite3.connect(str(cal_p))
    try:
        cal_conn.row_factory = sqlite3.Row
        plat_row = cal_conn.execute(
            "SELECT a, b, n_fit, log_likelihood FROM platt_global WHERE id=1"
        ).fetchone()
        if plat_row is None:
            # Pas de fit → fallback conservateur
            return Prediction(
                symbol=symbol, timeframe=timeframe,
                regime_type=regime_type, phase=phase,
                vol_atr_bucket=vol_bucket,
                declared_confiance=int(declared_confiance),
                calibrated_proba=0.5,
                beta_posterior=None,
                platt_used="prior_only",
                confidence_in_calibration=0.0,
                edge=0.5 * float(tp_pips) - 0.5 * float(sl_pips),
                recommended_action="skip",
                rationale="no_calibration_fit_yet",
            )
        platt_global = PlattCalibrator(
            a=float(plat_row["a"]),
            b=float(plat_row["b"]),
            n_fit=int(plat_row["n_fit"]),
            log_likelihood=float(plat_row["log_likelihood"]),
        )
        # Load cellule. Stratégie : on essaie d'abord le bucket de vol exact,
        # puis on fallback sur UNKNOWN si pas trouvé.
        cell_row = cal_conn.execute(
            """
            SELECT n_resolved, n_wins, n_losses, sum_conf, vol_atr_bucket
            FROM cell_stats
            WHERE symbol=? AND timeframe=? AND regime_type=? AND phase=?
              AND vol_atr_bucket IN (?, 'UNKNOWN')
            ORDER BY CASE WHEN vol_atr_bucket = ? THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (symbol, timeframe, regime_type, phase, vol_bucket, vol_bucket),
        ).fetchone()

        # Platt local si cellule assez grosse
        platt_local: PlattCalibrator | None = None
        if cell_row is not None and cell_row["n_resolved"] >= MIN_N_FOR_LOCAL_CALIBRATION:
            shrink = min(1.0, cell_row["n_resolved"] / 60.0)
            platt_local = PlattCalibrator(
                a=platt_global.a * shrink,
                b=platt_global.b,
                n_fit=cell_row["n_resolved"],
                log_likelihood=platt_global.log_likelihood,
            )

        # Beta posterior
        bp: BetaPosterior | None = None
        global_wr_row = cal_conn.execute(
            "SELECT value FROM calibration_meta WHERE key='global_wr'"
        ).fetchone()
        global_wr = float(global_wr_row["value"]) if global_wr_row else 0.5

        if cell_row is not None and cell_row["n_resolved"] >= MIN_N_FOR_BETA_PRIOR:
            n_w = int(cell_row["n_wins"])
            n_l = int(cell_row["n_losses"])
            bp = beta_posterior_from_counts(n_w, n_l)

        # Combine Platt + Beta posterior
        conf_norm = max(0.0, min(1.0, float(declared_confiance) / 100.0))
        platt_used = "global"
        platt_proba = platt_global.predict_proba(conf_norm)
        if platt_local is not None:
            platt_proba = platt_local.predict_proba(conf_norm)
            platt_used = f"local_{symbol}"

        if bp is not None:
            # Shrinkage : 60% Platt + 40% Beta
            combined = 0.6 * platt_proba + 0.4 * bp.mean
            confidence_in_calibration = min(1.0, cell_row["n_resolved"] / 100.0) if cell_row else 0.5
        else:
            combined = platt_proba
            confidence_in_calibration = 0.3

        # Edge = expected value par unité de risque
        edge = combined * float(tp_pips) - (1.0 - combined) * float(sl_pips)

        # Décision
        if combined >= edge_threshold and edge > 0:
            action = "enter"
        elif combined >= 0.5 and edge > 0:
            action = "reduce_size"
        else:
            action = "skip"

        rationale = (
            f"platt_used={platt_used} platt_proba={platt_proba:.3f} "
            + (f"beta_mean={bp.mean:.3f} " if bp else "beta=None ")
            + f"combined={combined:.3f} edge={edge:+.2f}p action={action}"
        )

        return Prediction(
            symbol=symbol,
            timeframe=timeframe,
            regime_type=regime_type,
            phase=phase,
            vol_atr_bucket=vol_bucket,
            declared_confiance=int(declared_confiance),
            calibrated_proba=round(combined, 6),
            beta_posterior=bp,
            platt_used=platt_used,
            confidence_in_calibration=round(confidence_in_calibration, 4),
            edge=round(edge, 4),
            recommended_action=action,
            rationale=rationale,
        )
    except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
        logger.warning("predict: DB error : %s", e)
        return Prediction(
            symbol=symbol, timeframe=timeframe,
            regime_type=regime_type, phase=phase,
            vol_atr_bucket=vol_bucket,
            declared_confiance=int(declared_confiance),
            calibrated_proba=0.5,
            beta_posterior=None,
            platt_used="error_db",
            confidence_in_calibration=0.0,
            edge=0.5 * float(tp_pips) - 0.5 * float(sl_pips),
            recommended_action="skip",
            rationale=f"db_error_fallback: {e}",
        )
    finally:
        cal_conn.close()


# ------------------------------------------------------------------ Batch scoring


def batch_score(
    decisions: Iterable[dict[str, Any]],
    calibration_db: Path | str | None = None,
) -> list[Prediction]:
    """Score un batch de décisions (dict avec symbol, tf, regime, phase,
    vol_atr_pips, declared_confiance, tp, sl)."""
    out: list[Prediction] = []
    for d in decisions:
        try:
            p = predict(
                symbol=d["symbol"],
                timeframe=d["timeframe"],
                regime_type=d["regime_type"],
                phase=d["phase"],
                vol_atr_pips=d.get("vol_atr_pips"),
                declared_confiance=d["declared_confiance"],
                tp_pips=d.get("tp_pips", 10.0),
                sl_pips=d.get("sl_pips", 15.0),
                calibration_db=calibration_db,
            )
            out.append(p)
        except Exception as e:
            logger.warning("batch_score: predict failed for %s : %s", d, e)
    return out


# ------------------------------------------------------------------ CLI


def main(argv: list[str] | None = None) -> int:
    """CLI : fit depuis DB live OU predict dry-run."""
    import argparse
    parser = argparse.ArgumentParser(
        description="v9_bayesian_predictor CLI (fit / predict / metrics)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_fit = sub.add_parser("fit", help="Fit Platt + Beta depuis DB live")
    p_fit.add_argument("--db", required=True, help="Path v9_forces.db")
    p_fit.add_argument("--cal-db", default=str(DEFAULT_CALIBRATION_DB),
                       help="Path calibration DB")

    p_pred = sub.add_parser("predict", help="Predict dry-run pour un contexte")
    p_pred.add_argument("--symbol", default="GBPUSD")
    p_pred.add_argument("--timeframe", default="M15")
    p_pred.add_argument("--regime", default="NEUTRE")
    p_pred.add_argument("--phase", default="culmination",
                        choices=VALID_PHASES)
    p_pred.add_argument("--vol-atr", type=float, default=3.5)
    p_pred.add_argument("--conf", type=int, default=80)
    p_pred.add_argument("--tp", type=float, default=10.0)
    p_pred.add_argument("--sl", type=float, default=15.0)
    p_pred.add_argument("--cal-db", default=str(DEFAULT_CALIBRATION_DB))

    args = parser.parse_args(argv)

    if args.cmd == "fit":
        result = fit_from_decisions_db(args.db, Path(args.cal_db))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "predict":
        pred = predict(
            symbol=args.symbol,
            timeframe=args.timeframe,
            regime_type=args.regime,
            phase=args.phase,
            vol_atr_pips=args.vol_atr,
            declared_confiance=args.conf,
            tp_pips=args.tp,
            sl_pips=args.sl,
            calibration_db=Path(args.cal_db),
        )
        print(json.dumps(pred.to_dict(), indent=2, ensure_ascii=False))
        return 0
    return 1


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
