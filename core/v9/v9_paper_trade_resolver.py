"""v9_paper_trade_resolver.py — Résolution paper-trade paramétrique (réconciliation 2026-07-20).

**Pourquoi ce module existe**
L'audit live du 2026-07-20 01h03 UTC a mesuré une divergence quasi-miroir entre
les deux moteurs de comptage :

| Source       | Résolution | WR    | Pips     |
|--------------|------------|-------|----------|
| `decisions`  | DYNAMIC    | 87.3% | +46 628  |
| `paper_trades` | fixe (héritée) | 23.8% | −47 374 |

Le moteur `paper_trades` applique un TP/SL uniforme sans considération du
**contexte** (timeframe, volatilité, session, confiance). Sur M1 Sydney en
vol_regime LOW, un TP serré est irréaliste (bruit intra-bar M1 = 8-12 pips) →
le SL se déclenche avant le TP → WR dégradé artificiellement.

Ce module fournit une **résolution paramétrique** : le TP/SL dépend du contexte
(tf × vol_regime), ajusté par confiance et session. Il est déterministe (R18 :
math pure, zéro LLM), défensif (R6 : ne crashe jamais l'appelant — l'appelant
gère le fallback), additif (R2).

**Mode de déploiement** : SHADOW uniquement (R25'). Le resolver *calcule* une
résolution alternative ; il n'écrase JAMAIS `paper_trades.is_win`. La promotion
en mode ACTIVE est conditionnée à une motion CEO explicite après validation.

**Note d'honnêteté (provenance)** : la table TP/SL de base est heuristique
(ordre de grandeur du bruit par timeframe). `calibrate_from_history()` la
re-calibre depuis la distribution empirique de `decisions.resolution_pips`,
mais utilise `resolution_pips` comme **proxy d'excursion** (le seul signal
disponible sans re-simuler les OHLC intrabar). Voir docstring de la méthode.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── Contexte & résultat ────────────────────────────────────────────

@dataclass
class ResolutionContext:
    """Contexte d'un trade, détermine le TP/SL à appliquer."""
    vol_regime: str  # "LOW" | "NORMAL" | "HIGH" | "EXTREME"
    session: str     # "sydney" | "asie" | "london" | "ny" | "new_york" | "overlap"
    timeframe: str   # "M1" | "M5" | "M15" | "H1" | "H4" | "D1"
    confiance: int   # 0-100
    symbol: str      # "GBPUSD" | "EURUSD" | ...
    direction: str   # "haussiere" | "baissiere"


@dataclass
class ResolvedOutcome:
    """Résultat d'une résolution paramétrique."""
    is_win: int       # 0 | 1
    pips: float
    exit_reason: str  # "tp" | "sl" | "horizon" | "timeout" | "risk_off"
    tp_used: float
    sl_used: float


# ── Table de base (tf, vol_regime) → (tp_pips, sl_pips) ─────────────
# Ordre de grandeur du bruit + amplitude directionnelle par timeframe.
# SL exprimé positif ici (magnitude) ; ResolvedOutcome.pips sera signé.
BASE_TABLE: dict[tuple[str, str], tuple[float, float]] = {
    ("M1", "LOW"): (8.0, 10.0),   ("M1", "NORMAL"): (12.0, 15.0),  ("M1", "HIGH"): (18.0, 22.0),
    ("M5", "LOW"): (15.0, 18.0),  ("M5", "NORMAL"): (22.0, 25.0),  ("M5", "HIGH"): (35.0, 40.0),
    ("M15", "LOW"): (30.0, 35.0), ("M15", "NORMAL"): (45.0, 50.0), ("M15", "HIGH"): (70.0, 80.0),
    ("H1", "LOW"): (60.0, 70.0),  ("H1", "NORMAL"): (90.0, 100.0), ("H1", "HIGH"): (140.0, 160.0),
}

# EXTREME dérivé de HIGH (×1.5) — pas de données propres, scaling conservateur.
EXTREME_SCALE = 1.5

# Multiplicateurs de session (vol relative). sydney/asie = calme, overlap = fort.
SESSION_MULTIPLIER: dict[str, float] = {
    "sydney": 0.7, "asie": 0.7,
    "london": 1.0,
    "ny": 1.0, "new_york": 1.0,
    "overlap": 1.1,
}
DEFAULT_SESSION_MULTIPLIER = 1.0

# Timeframe/vol de repli si contexte inconnu (le plus commun en live M1 Sydney).
FALLBACK_KEY = ("M1", "NORMAL")


class PaperTradeResolver:
    """Résout un trade paper selon son contexte (TP/SL paramétriques).

    Déterministe et défensif : `resolve()` ne lève jamais sur un contexte
    partiel — il retombe sur la table de repli. L'appelant reste responsable
    du fallback global (résolution héritée) s'il *instancie* mal le resolver.
    """

    def __init__(self, db_path: str, kill_switches_path: Optional[str] = None) -> None:
        """Charge les seuils adaptatifs depuis P3-WIRE (optionnel, best-effort).

        `db_path` sert à `calibrate_from_history`. `kill_switches_path` est
        accepté pour compat de signature (le resolver ne mute aucun kill
        switch — R6/R30). Aucun accès DB n'est fait à l'instanciation.
        """
        self.db_path = db_path
        self.kill_switches_path = kill_switches_path
        # Copie mutable de la table de base (surchargeable via set_table).
        self._table: dict[tuple[str, str], tuple[float, float]] = dict(BASE_TABLE)
        self._adaptive_threshold: Optional[float] = self._load_adaptive_threshold()

    def _load_adaptive_threshold(self) -> Optional[float]:
        """Best-effort : lit un seuil adaptatif P3-WIRE si disponible.

        Purement informatif (n'altère pas le TP/SL déterministe). Retourne
        None si le module P3-WIRE est absent — jamais de crash (R6)."""
        try:
            from core.v9._load_shared_context import load_shared_context  # type: ignore
            ctx = load_shared_context() or {}
            val = ctx.get("adaptive_antagonism_threshold")
            return float(val) if val is not None else None
        except Exception:  # noqa: BLE001 — P3-WIRE optionnel, jamais bloquant
            return None

    # ── TP/SL paramétrique ─────────────────────────────────────────

    def tp_sl_for(self, ctx: ResolutionContext) -> tuple[float, float]:
        """Retourne (tp_pips, sl_pips) — tous deux positifs (magnitudes).

        Pipeline :
          1. clé (timeframe, vol_regime) dans la table (EXTREME dérivé de HIGH).
          2. ajustement confiance : <70 → TP×0.8, SL×1.2 ; ≥90 → TP×1.2, SL×0.9.
          3. multiplicateur de session.
        """
        tf = (ctx.timeframe or "").upper()
        vol = (ctx.vol_regime or "").upper()

        if vol == "EXTREME":
            base = self._table.get((tf, "HIGH"))
            if base is not None:
                tp, sl = base[0] * EXTREME_SCALE, base[1] * EXTREME_SCALE
            else:
                tp, sl = self._fallback_tp_sl()
        else:
            base = self._table.get((tf, vol))
            tp, sl = base if base is not None else self._fallback_tp_sl()

        # Ajustement confiance.
        conf = ctx.confiance if ctx.confiance is not None else 70
        if conf < 70:
            tp, sl = tp * 0.8, sl * 1.2
        elif conf >= 90:
            tp, sl = tp * 1.2, sl * 0.9

        # Multiplicateur de session.
        mult = SESSION_MULTIPLIER.get((ctx.session or "").lower(), DEFAULT_SESSION_MULTIPLIER)
        tp, sl = tp * mult, sl * mult

        return round(tp, 2), round(sl, 2)

    def _fallback_tp_sl(self) -> tuple[float, float]:
        return self._table.get(FALLBACK_KEY, BASE_TABLE[FALLBACK_KEY])

    # ── Résolution ─────────────────────────────────────────────────

    def resolve(self, trade: dict, ctx: ResolutionContext) -> ResolvedOutcome:
        """Résout un trade selon son contexte.

        Modèle de résolution (déterministe, sur le pips réalisé disponible) :
          - `pips_realized` = trade["pips_simulated"] (excursion/résultat mesuré).
          - Si pips_realized >= tp  → TP touché (win, +tp).
          - Si pips_realized <= -sl → SL touché (loss, -sl).
          - Sinon (entre -sl et +tp) → sortie à horizon : is_win = pips>0,
            pips = pips_realized (le trade a expiré sans toucher les bornes).
          - Si pips_realized est None/absent → timeout (is_win=0).

        Ce modèle traite `pips_simulated` comme l'excursion finale mesurée :
        c'est un *proxy*, pas une re-simulation intrabar (voir docstring module).
        """
        tp, sl = self.tp_sl_for(ctx)

        raw = trade.get("pips_simulated", trade.get("pips"))
        if raw is None:
            return ResolvedOutcome(
                is_win=0, pips=0.0, exit_reason="timeout", tp_used=tp, sl_used=sl,
            )
        try:
            pips_realized = float(raw)
        except (TypeError, ValueError):
            return ResolvedOutcome(
                is_win=0, pips=0.0, exit_reason="timeout", tp_used=tp, sl_used=sl,
            )

        if pips_realized >= tp:
            return ResolvedOutcome(
                is_win=1, pips=tp, exit_reason="tp", tp_used=tp, sl_used=sl,
            )
        if pips_realized <= -sl:
            return ResolvedOutcome(
                is_win=0, pips=-sl, exit_reason="sl", tp_used=tp, sl_used=sl,
            )
        return ResolvedOutcome(
            is_win=1 if pips_realized > 0 else 0,
            pips=round(pips_realized, 2),
            exit_reason="horizon",
            tp_used=tp, sl_used=sl,
        )

    # ── Calibration depuis l'historique ────────────────────────────

    def calibrate_from_history(self, n_days: int = 30) -> dict[tuple[str, str], tuple[float, float]]:
        """Re-calibre la table (tf, vol_regime) → (tp, sl) depuis `decisions`.

        Algorithme (déterministe) :
          - Lit `decisions` résolues des N derniers jours (resolution_pips non NULL).
          - Groupe par (timeframe, vol_regime). vol_regime est extrait de
            `regime_type` normalisé (fallback 'NORMAL' — voir _regime_bucket).
          - Pour chaque groupe, balaye des facteurs d'échelle {0.5, 0.75, 1.0,
            1.25, 1.5} appliqués au TP/SL de base et retient celui qui maximise
            le score composite : WR × avg_win − (1−WR) × |avg_loss|, où WR/gains
            sont estimés en rejouant le modèle `resolve` sur resolution_pips.

        **Limite de provenance** : resolution_pips est un proxy d'excursion
        (pas de re-simulation OHLC). La table calibrée reflète donc la
        distribution finale des résolutions DYNAMIC, pas la dynamique intrabar.

        Retourne la nouvelle table (ne l'applique PAS — passer à `set_table`).
        Sur DB absente/vide → retourne la table courante inchangée (R6).
        """
        groups = self._fetch_history_groups(n_days)
        if not groups:
            return dict(self._table)

        candidate_scales = (0.5, 0.75, 1.0, 1.25, 1.5)
        new_table: dict[tuple[str, str], tuple[float, float]] = dict(self._table)

        for key, pips_list in groups.items():
            base = self._table.get(key)
            if base is None:
                continue
            best_scale, best_score = 1.0, float("-inf")
            for scale in candidate_scales:
                tp, sl = base[0] * scale, base[1] * scale
                score = self._score_table_entry(pips_list, tp, sl)
                if score > best_score:
                    best_score, best_scale = score, scale
            new_table[key] = (round(base[0] * best_scale, 2), round(base[1] * best_scale, 2))

        return new_table

    @staticmethod
    def _score_table_entry(pips_list: list[float], tp: float, sl: float) -> float:
        """Score composite d'un couple (tp, sl) sur une liste de pips réalisés.

        Rejoue le modèle `resolve` : pips>=tp → +tp ; pips<=-sl → -sl ; sinon
        pips brut. Score = WR × avg_win − (1−WR) × |avg_loss|. Déterministe."""
        if not pips_list:
            return float("-inf")
        wins: list[float] = []
        losses: list[float] = []
        for p in pips_list:
            if p >= tp:
                wins.append(tp)
            elif p <= -sl:
                losses.append(-sl)
            elif p > 0:
                wins.append(p)
            else:
                losses.append(p)
        n = len(pips_list)
        wr = len(wins) / n
        avg_win = (sum(wins) / len(wins)) if wins else 0.0
        avg_loss = (sum(losses) / len(losses)) if losses else 0.0
        return wr * avg_win - (1.0 - wr) * abs(avg_loss)

    def _fetch_history_groups(self, n_days: int) -> dict[tuple[str, str], list[float]]:
        """Lit `decisions` résolues sur N jours, groupé par (tf, vol_regime).

        Lecture seule stricte. Retourne {} sur toute erreur DB (R6)."""
        db_p = Path(self.db_path)
        if not db_p.exists():
            return {}
        try:
            conn = sqlite3.connect(f"file:{db_p}?mode=ro", uri=True, timeout=5.0)
        except sqlite3.OperationalError:
            return {}
        try:
            rows = conn.execute(
                """
                SELECT timeframe, regime_type, resolution_pips
                FROM decisions
                WHERE resolution_pips IS NOT NULL
                  AND resolved_at IS NOT NULL
                  AND resolved_at > datetime('now', ?)
                """,
                (f"-{int(max(0, n_days))} days",),
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
        finally:
            conn.close()

        groups: dict[tuple[str, str], list[float]] = {}
        for tf, regime, pips in rows:
            if pips is None or tf is None:
                continue
            key = (str(tf).upper(), self._regime_bucket(regime))
            groups.setdefault(key, []).append(float(pips))
        return groups

    @staticmethod
    def _regime_bucket(regime_type: Optional[str]) -> str:
        """Normalise `regime_type` en bucket vol_regime {LOW, NORMAL, HIGH}.

        `decisions` n'a pas de colonne vol_regime dédiée ; on projette le
        `regime_type` disponible. Inconnu → NORMAL (bucket majoritaire)."""
        if not regime_type:
            return "NORMAL"
        r = str(regime_type).lower()
        if any(k in r for k in ("calme", "range", "faible", "low", "compression")):
            return "LOW"
        if any(k in r for k in ("expansion", "volatil", "cassure", "high", "choc", "extreme")):
            return "HIGH"
        return "NORMAL"

    def set_table(self, table: dict[tuple[str, str], tuple[float, float]]) -> None:
        """Override la table TP/SL (utile après calibrate_from_history)."""
        self._table = dict(table)

    def get_table(self) -> dict[tuple[str, str], tuple[float, float]]:
        """Copie de la table courante (diagnostic / persistance)."""
        return dict(self._table)
