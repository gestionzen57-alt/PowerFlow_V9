"""v9_news_shock_attenuator.py — Phase 141 L19 News Shock Attenuator (2026-08-04).

Module additif (R2) qui module le sizing selon la fenetre news
(pre_news / imminent / post_news / normalisation / normal).
Defaut OFF (R25' strict motion CEO).
R6 fail-open : JAMAIS d'exception non capturee.

Audit SQL live 03/08 (R14 strict, n=337 paper_trades 30j) :
  - normal_spread (1.5-2.0) : n=215, WR 53.0%, PNL -245.8 pips
  - wide_spread (2.0-3.0, proxy news shock / NFP / CPI / FOMC) :
        n=122, WR 18.0%, PNL -619.4 pips, avg -5.08 pips/trade
  → les fenetres news detruisent 2.7x plus de pips par trade que
    le regime normal. WR chute de 35 pts. PNL total en fenetre
    news = -619 pips sur 30j → attenuateur = protection directe.

Logique :
  - 15 <= minutes_to_news <= 60 : ×0.5 (pre_news, 45 min d'attenuation)
  - 0  <= minutes_to_news < 15  : ×0.0 (imminent / HALT, 15 min blocage)
  - -15 <= minutes_to_news < 0  : ×0.5 (post_news, 15 min post-impact)
  - -60 <= minutes_to_news < -15: ×0.8 (normalisation, 45 min)
  - autre                       : ×1.0 (normal, hors fenetre)

Doctrine : R2 additif (NEW module), R6 fail-open, R7 tests verts,
           R18 code pur, R25' defaut OFF motion CEO.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from core.v9.kill_switches import get as ks_get

logger = logging.getLogger(__name__)

# ── Kill switch (defaut OFF, R25' strict) ─────────────────────────────
NEWS_SHOCK_ATTENUATOR_ENV = "V9_NEWS_SHOCK_ATTENUATOR_ENABLED"

# ── Fenetres de sizing (minutes_to_news = news_time - now) ───────────
# Bornes choisies par defaut, surchargeables via env (R2 additif).
WINDOW_PRE_NEWS_MIN = 15       # debut de la fenetre pre_news (min)
WINDOW_PRE_NEWS_MAX = 60       # fin de la fenetre pre_news (min)
WINDOW_IMMINENT_MIN = 0        # debut imminent
WINDOW_IMMINENT_MAX = 15       # fin imminent (HALT)
WINDOW_POST_NEWS_MIN = -15     # debut post_news (apres release)
WINDOW_POST_NEWS_MAX = 0       # fin post_news
WINDOW_NORMALISATION_MIN = -60 # debut normalisation
WINDOW_NORMALISATION_MAX = -15 # fin normalisation

# ── Multipliers (sortie de l'attenuateur) ────────────────────────────
MULT_PRE_NEWS = 0.5
MULT_IMMINENT = 0.0
MULT_POST_NEWS = 0.5
MULT_NORMALISATION = 0.8
MULT_NORMAL = 1.0
MULT_KILL_SWITCH_OFF = 1.0


# ── Kill switch accesseur (defaut OFF) ───────────────────────────────
def news_shock_attenuator_enabled() -> bool:
    """Kill switch V9_NEWS_SHOCK_ATTENUATOR_ENABLED — Phase 141.

    Active l'attenuateur news shock (fenetres NFP / CPI / FOMC / ECB).
    Defaut OFF (R25' strict motion CEO). Additif (R2), R6 fail-open.
    Module : core/v9/v9_news_shock_attenuator.py (NEW).
    """
    return ks_get(NEWS_SHOCK_ATTENUATOR_ENV, "0") == "1"


# ── Dataclass resultat ──────────────────────────────────────────────
@dataclass
class NewsWindowVerdict:
    """Verdict d'attenuation pour une fenetre news donnee."""
    minutes_to_news: int = 0
    multiplier: float = 1.0
    phase_label: str = "normal"
    enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "minutes_to_news": self.minutes_to_news,
            "multiplier": round(self.multiplier, 3),
            "phase_label": self.phase_label,
            "enabled": self.enabled,
        }


# ── API publique ────────────────────────────────────────────────────
def get_news_window_multiplier(minutes_to_news: int) -> tuple[float, str]:
    """Retourne (multiplier, phase_label) selon minutes_to_news.

    Logique (cf. en-tete module) :
      - 15 <= minutes_to_news <= 60 : ×0.5 (pre_news)
      - 0  <= minutes_to_news < 15  : ×0.0 (imminent / HALT)
      - -15 <= minutes_to_news < 0  : ×0.5 (post_news)
      - -60 <= minutes_to_news < -15: ×0.8 (normalisation)
      - autre                       : ×1.0 (normal)

    Args:
        minutes_to_news: difference en minutes entre now et l'heure
            de release de la news. Positif = avant, negatif = apres,
            0 = pile a l'heure de release.

    Returns:
        (multiplier, phase_label). Si kill switch OFF, retourne
        toujours (1.0, "kill_switch_off") — pass-through (R25').
    """
    if not news_shock_attenuator_enabled():
        # Pass-through (R25' defaut OFF, R6 fail-open).
        return MULT_KILL_SWITCH_OFF, "kill_switch_off"
    return _compute_multiplier(minutes_to_news)


def classify_news_window(minutes_to_news: int) -> NewsWindowVerdict:
    """Version dataclass de get_news_window_multiplier.

    Utile pour les consommateurs (tests, dashboard) qui veulent un
    verdict structure plutot qu'un tuple. Memes regles de fenetre.
    """
    enabled = news_shock_attenuator_enabled()
    if not enabled:
        return NewsWindowVerdict(
            minutes_to_news=int(minutes_to_news),
            multiplier=MULT_KILL_SWITCH_OFF,
            phase_label="kill_switch_off",
            enabled=False,
        )
    mult, label = _compute_multiplier(minutes_to_news)
    return NewsWindowVerdict(
        minutes_to_news=int(minutes_to_news),
        multiplier=mult,
        phase_label=label,
        enabled=True,
    )


def summarize_phase_distribution(verdicts: list[NewsWindowVerdict]) -> dict:
    """Agregat d'une liste de verdicts (helper pour dashboard / tests).

    Retourne : n_total, n_pre_news, n_imminent, n_post_news,
    n_normalisation, n_normal, n_kill_switch_off, multiplier_avg.
    """
    out = {
        "n_total": len(verdicts),
        "n_pre_news": 0,
        "n_imminent": 0,
        "n_post_news": 0,
        "n_normalisation": 0,
        "n_normal": 0,
        "n_kill_switch_off": 0,
        "multiplier_avg": 0.0,
    }
    if not verdicts:
        return out
    for v in verdicts:
        key = f"n_{v.phase_label}"
        if key in out:
            out[key] += 1
    out["multiplier_avg"] = round(
        sum(v.multiplier for v in verdicts) / len(verdicts), 3
    )
    return out


# ── Helpers internes (R18 code pur, R6 fail-open) ────────────────────
def _compute_multiplier(minutes_to_news: int) -> tuple[float, str]:
    """Calcul pur, sans I/O, sans LLM. Defaut OFF gere par l'appelant."""
    try:
        m = int(minutes_to_news)
    except (TypeError, ValueError):
        # R6 fail-open : entree invalide → on laisse passer.
        return MULT_NORMAL, "normal"

    if WINDOW_PRE_NEWS_MIN <= m <= WINDOW_PRE_NEWS_MAX:
        return MULT_PRE_NEWS, "pre_news"
    if WINDOW_IMMINENT_MIN <= m < WINDOW_IMMINENT_MAX:
        return MULT_IMMINENT, "imminent"
    if WINDOW_POST_NEWS_MIN <= m < WINDOW_POST_NEWS_MAX:
        return MULT_POST_NEWS, "post_news"
    if WINDOW_NORMALISATION_MIN <= m < WINDOW_NORMALISATION_MAX:
        return MULT_NORMALISATION, "normalisation"
    return MULT_NORMAL, "normal"
