"""market_regime_global.py — Détecteur risk-on / risk-off global (P3 quantique).

Le système lit chaque paire en haute définition, mais un trade ne vit pas dans
le vide : il vit dans un RÉGIME de marché global. Quand le monde est en
« risk-off » (fuite vers les valeurs refuges : USD, JPY, CHF), les cassures
échouent plus souvent et les objectifs ambitieux se paient cher. En
« risk-on » (appétit pour le risque : AUD, NZD, croissance), les tendances
portent plus loin.

Ce module dérive deux dimensions à partir des forces de devises (indices
0-100 déjà calculés et stockés dans `forces_snapshots`) :

  1. USD strength  : la force moyenne du dollar (force_usd) — le dollar mène
     la cotation de toutes nos paires (toutes sont XXXUSD ou USDXXX).
  2. Risk sentiment: appétit vs aversion, mesuré par l'écart entre les devises
     « risk-on » (AUD, NZD) et les refuges (JPY, CHF).

Le résultat est injecté (optionnellement) dans le DynamicRiskManager comme un
modulateur de TP : en risk-off on tempère l'ambition, en risk-on on l'assume.

Doctrine :
  - R18 : code pur, stdlib uniquement (sqlite3, statistics)
  - R2  : additif — détecteur isolé ; l'injection DRM est optionnelle et
          derrière kill switch (défaut OFF).
  - R6  : try/except, jamais bloquant ; régime NEUTRE par défaut.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from statistics import mean
from typing import Any

from core.v9.config import DB_PATH
from core.v9.db_schema import get_connection

log = logging.getLogger(__name__)

MARKET_REGIME_GLOBAL_VERSION = "1.0"

# ── Devises par catégorie ──────────────────────────────────────────
# Refuges (recherchés en aversion au risque) vs risk-on (recherchés en appétit).
SAFE_HAVENS = ("jpy", "chf")
RISK_ON_CCY = ("aud", "nzd")

# ── Seuils (échelle 0-100, neutre ≈ 50) ────────────────────────────
USD_STRONG_THRESHOLD = 55.0
USD_WEAK_THRESHOLD = 45.0
# Écart risk_on - refuges au-delà duquel on bascule le sentiment.
RISK_SENTIMENT_THRESHOLD = 8.0

# ── Modulation TP transmise au DRM ─────────────────────────────────
# risk-off → objectifs plus prudents ; risk-on → objectifs assumés.
TP_MOD_RISK_OFF = 0.85
TP_MOD_RISK_ON = 1.10
TP_MOD_NEUTRAL = 1.0

# Fenêtre de lecture : dernières N lignes (le plus récent bar cross-paires).
DEFAULT_LOOKBACK_ROWS = 30


@dataclass
class GlobalRegime:
    """Régime de marché global (risk-on/off + force USD)."""

    usd_strength: float = 50.0
    usd_regime: str = "usd_neutral"        # usd_strong | usd_weak | usd_neutral
    risk_sentiment: str = "neutral"        # risk_on | risk_off | neutral
    risk_score: float = 0.0                # écart risk_on - refuges (signé)
    tp_modulation: float = TP_MOD_NEUTRAL
    n_samples: int = 0
    source: str = "computed"               # computed | fallback
    detail: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "usd_strength": round(self.usd_strength, 2),
            "usd_regime": self.usd_regime,
            "risk_sentiment": self.risk_sentiment,
            "risk_score": round(self.risk_score, 2),
            "tp_modulation": round(self.tp_modulation, 3),
            "n_samples": self.n_samples,
            "source": self.source,
            "detail": {k: round(v, 2) for k, v in self.detail.items()},
            "version": MARKET_REGIME_GLOBAL_VERSION,
        }


def classify(
    force_means: dict[str, float],
    n_samples: int,
) -> GlobalRegime:
    """Classe le régime à partir des forces moyennes par devise (pur).

    Args:
        force_means : {"usd": 52.1, "jpy": 40.0, "chf": 60.0, "aud": 70.0, ...}
        n_samples   : nombre d'échantillons agrégés.

    Returns:
        GlobalRegime.
    """
    usd = force_means.get("usd", 50.0)

    # USD regime
    if usd >= USD_STRONG_THRESHOLD:
        usd_regime = "usd_strong"
    elif usd <= USD_WEAK_THRESHOLD:
        usd_regime = "usd_weak"
    else:
        usd_regime = "usd_neutral"

    # Risk sentiment : appétit (AUD/NZD) vs refuges (JPY/CHF).
    haven_vals = [force_means[c] for c in SAFE_HAVENS if c in force_means]
    risk_vals = [force_means[c] for c in RISK_ON_CCY if c in force_means]
    haven_strength = mean(haven_vals) if haven_vals else 50.0
    risk_strength = mean(risk_vals) if risk_vals else 50.0
    risk_score = risk_strength - haven_strength

    if risk_score >= RISK_SENTIMENT_THRESHOLD:
        sentiment = "risk_on"
        tp_mod = TP_MOD_RISK_ON
    elif risk_score <= -RISK_SENTIMENT_THRESHOLD:
        sentiment = "risk_off"
        tp_mod = TP_MOD_RISK_OFF
    else:
        sentiment = "neutral"
        tp_mod = TP_MOD_NEUTRAL

    return GlobalRegime(
        usd_strength=usd,
        usd_regime=usd_regime,
        risk_sentiment=sentiment,
        risk_score=risk_score,
        tp_modulation=tp_mod,
        n_samples=n_samples,
        source="computed",
        detail={
            "haven_strength": haven_strength,
            "risk_strength": risk_strength,
            **{c: force_means[c] for c in force_means},
        },
    )


class MarketRegimeGlobal:
    """Dérive le régime global depuis les forces de devises récentes."""

    def __init__(self, db_path: Any = None) -> None:
        self.db_path = db_path if db_path is not None else DB_PATH

    def _connect(self) -> sqlite3.Connection:
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def detect(self, lookback_rows: int = DEFAULT_LOOKBACK_ROWS) -> GlobalRegime:
        """Lit les dernières forces et retourne le régime global. R6 : jamais
        d'exception — régime NEUTRE (source=fallback) en cas d'échec."""
        try:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT force_usd, force_jpy, force_chf, force_aud,
                           force_nzd, force_gbp, force_eur, force_cad
                    FROM forces_snapshots
                    WHERE force_usd IS NOT NULL
                    ORDER BY bar_time DESC
                    LIMIT ?
                    """,
                    (lookback_rows,),
                ).fetchall()
            finally:
                conn.close()

            if not rows:
                return GlobalRegime(source="fallback")

            cols = {
                "usd": "force_usd", "jpy": "force_jpy", "chf": "force_chf",
                "aud": "force_aud", "nzd": "force_nzd", "gbp": "force_gbp",
                "eur": "force_eur", "cad": "force_cad",
            }
            force_means: dict[str, float] = {}
            for key, col in cols.items():
                vals = [r[col] for r in rows if r[col] is not None]
                if vals:
                    force_means[key] = float(mean(vals))
            if "usd" not in force_means:
                return GlobalRegime(source="fallback")
            return classify(force_means, n_samples=len(rows))
        except Exception as exc:
            log.debug("market_regime_global: detect failed: %s", exc)
            return GlobalRegime(source="fallback")
