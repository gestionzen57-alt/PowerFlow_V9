"""v9_edge_decay_sentinel — Phase 140 L18 Edge Decay Sentinel (2026-08-03).

Sentinel de degradation edge par principe. Surveille en continu le WR
recent vs baseline et propose une action preventive AVANT que la perte
ne se materialise.

Audit SQL live 03/08 (n=337 paper_trades) :
  - 34 principes distincts sur les trades.
  - 21/21 principes eligibility (n>=30) ont delta_wr < -10% sur les
    20 derniers trades vs baseline (degradation systemique).
  - 21/21 ont pnl recent < 0 (pnl cumule -83 a -125 pips sur 20 trades).
  - Top decay : ELASTIC_BREATH (-33.9%), GRAVITY_RESPRING_NODE (-32.9%),
    PRICE_LAG_AT_NODE_BIRTH (-27.9%).
  - pnl cumule recent (20 derniers) sur les 21 principes : ~ -2100 pips.
    Gain projeté Phase 140 (blacklist 24h des pires) : 60-120 pips
    evites par cycle.

Logique :
  - delta_wr = wr_recent - wr_baseline (en points %).
  - pnl_recent < 0  → DEMOTION (principe perd de l'argent sur la fenetre).
  - delta_wr < -10% → BLACKLIST_TEMP_24H (WR chute brutale).
  - delta_wr < -5%  → OBSERVATION_ONLY (surveiller sans action lourde).
  - sinon           → NONE (principe stable).

Le sentinel est distinct du Monitor historique (edge_decay_monitor.py) :
  - Monitor = surveillance multi-fenetre + auto-actions. R25'' actif.
  - Sentinel = diagnostic + recommandation par principe, lecture seule.
    Defaut OFF (R25' strict motion CEO).

Doctrine : R2 additif (NEW module), R6 fail-open, R7 tests verts,
           R18 code pur, R25' defaut OFF motion CEO.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.v9.kill_switches import get as ks_get

logger = logging.getLogger(__name__)

# ── Kill switch (defaut OFF, R25' strict) ─────────────────────────────
EDGE_DECAY_SENTINEL_ENV = "V9_EDGE_DECAY_SENTINEL_ENABLED"

# ── Seuils (cf. audit SQL live 03/08) ────────────────────────────────
DECAY_WR_DROP_PCT = 10.0      # -10% WR recent vs baseline → BLACKLIST_TEMP
DECAY_WR_DROP_OBS_PCT = 5.0   # -5%  WR recent vs baseline → OBSERVATION_ONLY
PNL_RECENT_DEMOTION = 0.0     # pnl recent < 0 → DEMOTION
MIN_TRADES_BASELINE = 30      # min trades pour qualifier un principe
MIN_TRADES_RECENT = 10        # min trades dans la fenetre recent
N_RECENT_DEFAULT = 20
N_BASELINE_DEFAULT = 100

# ── DB par defaut ────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = ROOT / "data" / "v9_forces.db"


# ── Kill switch accesseur (defaut OFF) ───────────────────────────────
def edge_decay_sentinel_enabled() -> bool:
    """Kill switch V9_EDGE_DECAY_SENTINEL_ENABLED — Phase 140.

    Sentinel de degradation edge (proactif vs reactif). Defaut OFF
    (R25' strict motion CEO). Additif (R2). R6 fail-open.
    """
    return ks_get(EDGE_DECAY_SENTINEL_ENV, "0") == "1"


# ── Dataclass resultat ──────────────────────────────────────────────
@dataclass
class DecayReport:
    """Rapport de degradation pour un principe."""
    principle_id: str = ""
    n_baseline: int = 0
    n_recent: int = 0
    wr_baseline_pct: float = 0.0
    wr_recent_pct: float = 0.0
    wr_delta_pct: float = 0.0
    pnl_baseline: float = 0.0
    pnl_recent: float = 0.0
    pnl_delta: float = 0.0
    decay_score: float = 0.0     # 0.0 (stable) → 1.0 (decay severe)
    decay_detected: bool = False
    recommended_action: str = "NONE"  # NONE | OBSERVATION_ONLY | DEMOTION | BLACKLIST_TEMP_24H

    def to_dict(self) -> dict[str, Any]:
        return {
            "principle_id": self.principle_id,
            "n_baseline": self.n_baseline,
            "n_recent": self.n_recent,
            "wr_baseline_pct": round(self.wr_baseline_pct, 2),
            "wr_recent_pct": round(self.wr_recent_pct, 2),
            "wr_delta_pct": round(self.wr_delta_pct, 2),
            "pnl_baseline": round(self.pnl_baseline, 2),
            "pnl_recent": round(self.pnl_recent, 2),
            "pnl_delta": round(self.pnl_delta, 2),
            "decay_score": round(self.decay_score, 3),
            "decay_detected": self.decay_detected,
            "recommended_action": self.recommended_action,
        }


# ── Helpers SQL ─────────────────────────────────────────────────────
def _load_trades_by_principle(
    db_path: Path = DEFAULT_DB,
    table: str = "paper_trades",
    col_src: str = "principes_source",
    col_pips: str = "pips_net_of_spread",
    col_win: str = "is_win",
    col_ts: str = "opened_at",
) -> dict[str, list[tuple[str, float, int]]]:
    """Charge tous les paper_trades et groupe par principe.

    Returns: {principle_id: [(opened_at, pips, is_win), ...]} tries par
             timestamp ASC (ordre temporel).
    """
    out: dict[str, list[tuple[str, float, int]]] = defaultdict(list)
    if not db_path.exists():
        return out
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT {col_src}, {col_pips}, {col_win}, {col_ts} "
                f"FROM {table} WHERE {col_src} IS NOT NULL AND {col_src} != '' "
                f"ORDER BY {col_ts} ASC"
            )
            for src, pips, iswin, opened in cur.fetchall():
                if not src:
                    continue
                try:
                    if isinstance(src, str) and src.strip().startswith("["):
                        arr = json.loads(src)
                    else:
                        arr = [p.strip() for p in str(src).split(",") if p.strip()]
                except Exception:
                    continue
                pips_f = float(pips) if pips is not None else 0.0
                iswin_i = int(iswin) if iswin is not None else 0
                for p in arr:
                    out[p].append((str(opened), pips_f, iswin_i))
    except Exception as e:  # R6 fail-open
        logger.warning("edge_decay_sentinel: DB load failed: %s", e)
        return {}
    return out


def _score(report: DecayReport) -> DecayReport:
    """Calcule decay_score, decay_detected, recommended_action.

    Logique :
      - decay_score = clip((baseline_wr - recent_wr) / 0.30, 0, 1)
        (0.30 = decay "max" normalisé sur la distribution observee 03/08).
      - decay_detected = (delta_wr < -DECAY_WR_DROP_OBS_PCT) ou (pnl_recent < 0).
      - recommended_action :
          BLACKLIST_TEMP_24H  si delta_wr < -DECAY_WR_DROP_PCT
          DEMOTION            si pnl_recent < 0 (apres recent check)
          OBSERVATION_ONLY    si delta_wr < -DECAY_WR_DROP_OBS_PCT
          NONE                sinon
    Priorite : BLACKLIST > DEMOTION > OBSERVATION > NONE.
    """
    delta = report.wr_delta_pct  # en points % (negatif = degradation)
    score = max(0.0, min(1.0, (-delta) / 30.0))
    report.decay_score = round(score, 3)

    action = "NONE"
    if delta < -DECAY_WR_DROP_PCT:
        action = "BLACKLIST_TEMP_24H"
    elif report.pnl_recent < PNL_RECENT_DEMOTION:
        action = "DEMOTION"
    elif delta < -DECAY_WR_DROP_OBS_PCT:
        action = "OBSERVATION_ONLY"
    report.recommended_action = action

    report.decay_detected = action != "NONE"
    return report


# ── API publique ────────────────────────────────────────────────────
def analyze_principle_decay(
    principle_id: str,
    n_recent_trades: int = N_RECENT_DEFAULT,
    n_baseline_trades: int = N_BASELINE_DEFAULT,
    trades: list[tuple[str, float, int]] | None = None,
    db_path: Path = DEFAULT_DB,
) -> dict:
    """Analyse la degradation d'un principe (lecture seule).

    Args:
        principle_id: identifiant du principe (ex. 'ELASTIC_BREATH').
        n_recent_trades: nb derniers trades pris comme fenetre "recent".
        n_baseline_trades: nb max de trades avant la fenetre recent
            pour calculer la baseline.
        trades: si fourni, utilise cette liste (tests). Sinon, charge
            depuis paper_trades via _load_trades_by_principle.
        db_path: chemin DB (override pour tests).

    Returns:
        dict avec wr_recent_pct, wr_baseline_pct, wr_delta, pnl_recent,
        pnl_baseline, pnl_delta, decay_score, decay_detected,
        recommended_action. Si pas assez de trades → tous les compteurs
        a 0 et decay_detected=False.
    """
    if not edge_decay_sentinel_enabled():
        # Sentinel OFF → pass-through (R25' defaut OFF).
        # Court-circuit AVANT toute lecture DB ou calcul, meme si
        # `trades` est injecte par les tests. Cela garantit qu'aucun
        # consommateur ne peut obtenir un verdict de decay quand le
        # kill switch est OFF.
        return DecayReport(principle_id=principle_id).to_dict()
    if trades is None:
        all_trades = _load_trades_by_principle(db_path=db_path)
        trades = all_trades.get(principle_id, [])

    if not trades or len(trades) < MIN_TRADES_BASELINE:
        return DecayReport(principle_id=principle_id).to_dict()

    # Split recent vs baseline (ordre temporel ASC).
    baseline = trades[:-n_recent_trades] if len(trades) > n_recent_trades else []
    recent = trades[-n_recent_trades:]

    if len(baseline) < MIN_TRADES_BASELINE or len(recent) < MIN_TRADES_RECENT:
        return DecayReport(principle_id=principle_id).to_dict()

    # Optionnel : borner baseline a n_baseline_trades les plus recents
    # avant la fenetre recent.
    if len(baseline) > n_baseline_trades:
        baseline = baseline[-n_baseline_trades:]

    n_b = len(baseline)
    n_r = len(recent)
    wr_b = sum(t[2] for t in baseline) / n_b * 100.0
    wr_r = sum(t[2] for t in recent) / n_r * 100.0
    pnl_b = sum(t[1] for t in baseline)
    pnl_r = sum(t[1] for t in recent)

    rep = DecayReport(
        principle_id=principle_id,
        n_baseline=n_b,
        n_recent=n_r,
        wr_baseline_pct=wr_b,
        wr_recent_pct=wr_r,
        wr_delta_pct=wr_r - wr_b,
        pnl_baseline=pnl_b,
        pnl_recent=pnl_r,
        pnl_delta=pnl_r - pnl_b,
    )
    _score(rep)
    return rep.to_dict()


def scan_all_principles_decay(
    n_recent: int = N_RECENT_DEFAULT,
    n_baseline: int = N_BASELINE_DEFAULT,
    db_path: Path = DEFAULT_DB,
) -> list[dict]:
    """Scan tous les principes et retourne ceux en degradation.

    Args:
        n_recent, n_baseline: forwarding vers analyze_principle_decay.
        db_path: chemin DB.

    Returns:
        Liste de dicts tries par decay_score DESC. Liste vide si sentinel
        OFF ou DB absente (R6 fail-open).
    """
    if not edge_decay_sentinel_enabled():
        return []  # pass-through
    all_trades = _load_trades_by_principle(db_path=db_path)
    if not all_trades:
        return []
    out: list[dict] = []
    for pid in all_trades.keys():
        rep = analyze_principle_decay(
            principle_id=pid,
            n_recent_trades=n_recent,
            n_baseline_trades=n_baseline,
            trades=all_trades[pid],
        )
        out.append(rep)
    # Tri par decay_score DESC puis pnl_recent ASC (pires en premier).
    out.sort(key=lambda r: (-r["decay_score"], r["pnl_recent"]))
    return out


def summarize_scan(reports: list[dict]) -> dict:
    """Agregat des resultats d'un scan (helper pour dashboard / tests)."""
    if not reports:
        return {"n_principles": 0, "n_decay": 0, "n_blacklist": 0,
                "n_demote": 0, "n_observation": 0, "pnl_recent_total": 0.0}
    return {
        "n_principles": len(reports),
        "n_decay": sum(1 for r in reports if r["decay_detected"]),
        "n_blacklist": sum(1 for r in reports if r["recommended_action"] == "BLACKLIST_TEMP_24H"),
        "n_demote": sum(1 for r in reports if r["recommended_action"] == "DEMOTION"),
        "n_observation": sum(1 for r in reports if r["recommended_action"] == "OBSERVATION_ONLY"),
        "pnl_recent_total": round(sum(r["pnl_recent"] for r in reports), 2),
    }
