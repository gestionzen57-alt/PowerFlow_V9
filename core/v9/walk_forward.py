"""walk_forward.py — Validation walk-forward (edge réel vs overfitting).

Un edge mesuré sur tout l'historique peut être un artefact d'optimisation :
le seuil « optimal » a été choisi APRÈS avoir vu les données. La validation
walk-forward répond à la seule question qui compte pour un stratège
institutionnel :

    « Un seuil calibré sur le PASSÉ tient-il sur le FUTUR jamais vu ? »

Méthode (anchored walk-forward) :
  1. On trie les décisions résolues par timestamp croissant.
  2. On découpe l'historique en N fenêtres contiguës (défaut 5).
  3. Pour chaque frontière k (1..N-1) :
       - in-sample  = fenêtres [0..k-1]  (le passé connu)
       - out-of-sample = fenêtre [k]      (le futur jamais vu)
       - on CALIBRE le seuil de confiance qui maximise l'expectancy
         in-sample (grid search, plancher de trades)
       - on APPLIQUE ce seuil out-of-sample et on mesure l'expectancy réelle
  4. Verdict : si l'expectancy out-of-sample moyenne reste positive et ne
     s'effondre pas face à l'in-sample → edge réel. Sinon → overfitting.

Doctrine :
  - R18 : code pur, stdlib uniquement (math, statistics, sqlite3)
  - R2  : additif — lecture seule, ne modifie aucune calibration live
  - R6  : try/except, jamais bloquant
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.config import DB_PATH
from core.v9.db_schema import get_connection
from core.v9.edge_validator import _normal_cdf

WALK_FORWARD_VERSION = "1.0"

# Nombre de fenêtres contiguës (5 = standard institutionnel).
DEFAULT_N_WINDOWS = 5

# Grille de seuils de confiance testés en calibration in-sample.
CONFIANCE_GRID = [0, 50, 55, 60, 65, 70, 75, 80, 85, 90]

# Plancher de trades pour qu'un seuil in-sample soit retenu (évite de
# calibrer sur 3 trades chanceux).
MIN_INSAMPLE_TRADES = 20

# Plancher de trades out-of-sample pour qu'un fold compte dans le verdict.
MIN_OOS_TRADES = 10

# Ratio de dégradation OOS/IS en-dessous duquel on suspecte l'overfitting.
DEGRADATION_WARN_RATIO = 0.5


@dataclass
class FoldResult:
    """Résultat d'un fold walk-forward (calibration IS → test OOS)."""

    fold_index: int
    threshold: int
    is_n: int
    is_expectancy: float
    oos_n: int
    oos_expectancy: float
    oos_win_rate: float
    oos_p_value: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold_index": self.fold_index,
            "threshold": self.threshold,
            "is_n": self.is_n,
            "is_expectancy": round(self.is_expectancy, 3),
            "oos_n": self.oos_n,
            "oos_expectancy": round(self.oos_expectancy, 3),
            "oos_win_rate": round(self.oos_win_rate, 2),
            "oos_p_value": round(self.oos_p_value, 6),
        }


@dataclass
class WalkForwardReport:
    """Rapport agrégé de la validation walk-forward."""

    n_trades: int
    n_windows: int
    folds: list[FoldResult] = field(default_factory=list)
    mean_is_expectancy: float = 0.0
    mean_oos_expectancy: float = 0.0
    degradation_ratio: float = 0.0
    oos_positive_folds: int = 0
    pooled_oos_p_value: float = 1.0
    verdict: str = "INDETERMINE"
    scope: str = "all"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": WALK_FORWARD_VERSION,
            "scope": self.scope,
            "n_trades": self.n_trades,
            "n_windows": self.n_windows,
            "mean_is_expectancy": round(self.mean_is_expectancy, 3),
            "mean_oos_expectancy": round(self.mean_oos_expectancy, 3),
            "degradation_ratio": round(self.degradation_ratio, 3),
            "oos_positive_folds": self.oos_positive_folds,
            "pooled_oos_p_value": round(self.pooled_oos_p_value, 6),
            "verdict": self.verdict,
            "folds": [f.to_dict() for f in self.folds],
        }


def _expectancy(pips: list[float]) -> float:
    return sum(pips) / len(pips) if pips else 0.0


def _t_test_p_value(pips: list[float]) -> float:
    """p-value du test t (H0: expectancy = 0), approximation normale."""
    n = len(pips)
    if n < 2:
        return 1.0
    mean = _expectancy(pips)
    var = sum((p - mean) ** 2 for p in pips) / (n - 1)
    std = math.sqrt(var)
    if std <= 0:
        return 0.0 if mean != 0 else 1.0
    t_stat = mean / (std / math.sqrt(n))
    return 2 * (1 - _normal_cdf(abs(t_stat)))


class WalkForwardValidator:
    """Valide qu'un edge tient hors-échantillon (walk-forward)."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH

    def _connect(self) -> sqlite3.Connection:
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _fetch_resolved(
        self, symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """Décisions résolues, triées par timestamp (le sens du temps compte).

        Chaque item : {confiance, pips, is_win}. R6 : liste vide si erreur.
        """
        conn = self._connect()
        try:
            sql = (
                "SELECT timestamp, confiance, resolution_pips, is_win "
                "FROM decisions "
                "WHERE is_win IS NOT NULL AND resolution_pips IS NOT NULL"
            )
            params: tuple[Any, ...] = ()
            if symbol:
                sql += " AND symbol = ?"
                params = (symbol,)
            sql += " ORDER BY timestamp ASC"
            rows = conn.execute(sql, params).fetchall()
            out: list[dict[str, Any]] = []
            for r in rows:
                out.append({
                    "confiance": int(r["confiance"] or 0),
                    "pips": float(r["resolution_pips"] or 0.0),
                    "is_win": int(r["is_win"]),
                })
            return out
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    @staticmethod
    def _calibrate_threshold(
        in_sample: list[dict[str, Any]],
    ) -> tuple[int, float, int]:
        """Cherche le seuil de confiance maximisant l'expectancy in-sample.

        Returns (threshold, expectancy, n_selected). Le seuil retenu doit
        laisser au moins MIN_INSAMPLE_TRADES trades ; sinon on retombe sur
        le seuil 0 (tous les trades) pour rester honnête.
        """
        best_thr = 0
        best_exp = float("-inf")
        best_n = 0
        for thr in CONFIANCE_GRID:
            pips = [t["pips"] for t in in_sample if t["confiance"] >= thr]
            if len(pips) < MIN_INSAMPLE_TRADES:
                continue
            exp = _expectancy(pips)
            if exp > best_exp:
                best_exp = exp
                best_thr = thr
                best_n = len(pips)
        if best_n == 0:  # aucun seuil valide → tout l'échantillon
            pips = [t["pips"] for t in in_sample]
            return 0, _expectancy(pips), len(pips)
        return best_thr, best_exp, best_n

    def run(
        self,
        n_windows: int = DEFAULT_N_WINDOWS,
        symbol: str | None = None,
    ) -> WalkForwardReport:
        """Exécute la validation walk-forward complète."""
        trades = self._fetch_resolved(symbol=symbol)
        scope = symbol or "all"
        report = WalkForwardReport(
            n_trades=len(trades), n_windows=n_windows, scope=scope,
        )

        if len(trades) < n_windows * (MIN_INSAMPLE_TRADES + MIN_OOS_TRADES):
            report.verdict = "DONNEES_INSUFFISANTES"
            return report

        # Découpe en N fenêtres contiguës (par comptage, ordre temporel).
        size = len(trades) // n_windows
        windows = [
            trades[i * size: (i + 1) * size] for i in range(n_windows - 1)
        ]
        windows.append(trades[(n_windows - 1) * size:])  # le reste dans la dernière

        pooled_oos_pips: list[float] = []
        is_exps: list[float] = []
        oos_exps: list[float] = []

        for k in range(1, n_windows):
            in_sample = [t for w in windows[:k] for t in w]
            out_sample = windows[k]

            thr, is_exp, is_n = self._calibrate_threshold(in_sample)
            oos_pips = [t["pips"] for t in out_sample if t["confiance"] >= thr]
            oos_wins = [
                t for t in out_sample
                if t["confiance"] >= thr and t["is_win"] == 1
            ]
            oos_n = len(oos_pips)
            if oos_n < MIN_OOS_TRADES:
                continue

            oos_exp = _expectancy(oos_pips)
            oos_wr = len(oos_wins) / oos_n * 100 if oos_n else 0.0
            oos_p = _t_test_p_value(oos_pips)

            report.folds.append(FoldResult(
                fold_index=k,
                threshold=thr,
                is_n=is_n,
                is_expectancy=is_exp,
                oos_n=oos_n,
                oos_expectancy=oos_exp,
                oos_win_rate=oos_wr,
                oos_p_value=oos_p,
            ))
            is_exps.append(is_exp)
            oos_exps.append(oos_exp)
            pooled_oos_pips.extend(oos_pips)

        if not report.folds:
            report.verdict = "DONNEES_INSUFFISANTES"
            return report

        report.mean_is_expectancy = _expectancy(is_exps)
        report.mean_oos_expectancy = _expectancy(oos_exps)
        report.oos_positive_folds = sum(1 for e in oos_exps if e > 0)
        report.pooled_oos_p_value = _t_test_p_value(pooled_oos_pips)
        report.degradation_ratio = (
            report.mean_oos_expectancy / report.mean_is_expectancy
            if report.mean_is_expectancy > 0 else 0.0
        )
        report.verdict = self._verdict(report)
        return report

    @staticmethod
    def _verdict(report: WalkForwardReport) -> str:
        """Détermine le verdict à partir des métriques agrégées."""
        n_folds = len(report.folds)
        majority = report.oos_positive_folds > n_folds / 2
        oos_positive = report.mean_oos_expectancy > 0
        significant = report.pooled_oos_p_value < 0.05

        if oos_positive and majority and significant:
            if report.degradation_ratio >= DEGRADATION_WARN_RATIO:
                return "EDGE_REEL"
            return "EDGE_REEL_DEGRADE"  # positif OOS mais dégradation forte vs IS
        if not oos_positive:
            return "OVERFITTING"
        return "NON_CONCLUANT"  # positif mais non significatif / minoritaire


def render_markdown(report: WalkForwardReport, generated_at: str | None = None) -> str:
    """Rend le rapport walk-forward en Markdown."""
    ts = generated_at or datetime.now(timezone.utc).isoformat()
    verdict_emoji = {
        "EDGE_REEL": "✅ EDGE RÉEL",
        "EDGE_REEL_DEGRADE": "🟡 EDGE RÉEL (dégradé)",
        "OVERFITTING": "🔴 OVERFITTING",
        "NON_CONCLUANT": "⚪ NON CONCLUANT",
        "DONNEES_INSUFFISANTES": "⚫ DONNÉES INSUFFISANTES",
        "INDETERMINE": "⚫ INDÉTERMINÉ",
    }.get(report.verdict, report.verdict)

    lines = [
        f"# Walk-Forward Validation — {report.scope}",
        "",
        f"> Généré : {ts}",
        f"> Version : {WALK_FORWARD_VERSION}",
        "",
        f"## Verdict : {verdict_emoji}",
        "",
        f"- **Trades résolus** : {report.n_trades}",
        f"- **Fenêtres** : {report.n_windows} ({len(report.folds)} folds testés)",
        f"- **Expectancy in-sample moyenne** : {report.mean_is_expectancy:.3f} pips",
        f"- **Expectancy out-of-sample moyenne** : {report.mean_oos_expectancy:.3f} pips",
        f"- **Ratio de dégradation OOS/IS** : {report.degradation_ratio:.2f}",
        f"- **Folds OOS positifs** : {report.oos_positive_folds}/{len(report.folds)}",
        f"- **p-value OOS agrégée** : {report.pooled_oos_p_value:.6f}",
        "",
        "## ⚠️ Provenance des données",
        "",
        "Cette validation lit `decisions.resolution_pips` / `decisions.is_win`,",
        "produits par le **résolveur offline**. Ce résolveur n'est pas",
        "path-dependent (il ne rejoue pas TP/SL barre par barre comme",
        "`ExitSimulator` en clôture live) : un WR out-of-sample de 95-99 %",
        "est le symptôme de cet **artefact de résolution** (biais de",
        "distribution documenté), PAS d'un edge réellement exploitable à ce",
        "niveau. À lire donc en **valeur relative** : la _stabilité_ du seuil",
        "calibré (in-sample vs out-of-sample) et la _dégradation entre folds_",
        "restent des signaux valides ; le niveau absolu de WR/expectancy est",
        "gonflé par la résolution offline et ne doit pas être pris au pied",
        "de la lettre. La vérité live vient de `close_open_trades()` +",
        "`ExitSimulator` (≈ breakeven après coûts).",
        "",
        "## Détail par fold",
        "",
        "| Fold | Seuil conf. | IS n | IS exp. | OOS n | OOS exp. | OOS WR | OOS p |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for f in report.folds:
        lines.append(
            f"| {f.fold_index} | ≥{f.threshold} | {f.is_n} | "
            f"{f.is_expectancy:.3f} | {f.oos_n} | {f.oos_expectancy:.3f} | "
            f"{f.oos_win_rate:.1f}% | {f.oos_p_value:.4f} |"
        )
    lines.extend([
        "",
        "## Interprétation",
        "",
        "- **EDGE RÉEL** : l'expectancy tient hors-échantillon (OOS positif,",
        "  majoritaire, significatif) et ne s'effondre pas face à l'in-sample.",
        "- **EDGE RÉEL (dégradé)** : OOS positif et significatif mais forte",
        "  dégradation vs in-sample (ratio < 0.5) — edge réel mais sur-estimé.",
        "- **OVERFITTING** : l'expectancy OOS moyenne est négative — le seuil",
        "  calibré sur le passé ne survit pas au futur.",
        "- **NON CONCLUANT** : OOS positif mais non significatif ou minoritaire.",
        "",
    ])
    return "\n".join(lines)
