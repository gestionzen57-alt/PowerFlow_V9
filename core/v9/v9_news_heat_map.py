"""v9_news_heat_map.py — Phase 143 L20 News Heat Map (2026-08-04).

Module additif (R2) qui module le sizing selon la chaleur de la reaction
historique d'une paire a un type de news (NFP / CPI / FOMC / ECB).

Hypothese : certaines paires reagissent plus violemment a certains
types de news que d'autres. La heat map encode le multiplicateur
de base par (symbol, news_type), qui est ensuite combine avec la
fenetre news (minutes_to_news) du L19 attenuator.

Audit SQL live 03/08 (R14 strict, n=337 paper_trades 60j, jointure
paper_trades x forces_snapshots pour recuperer le symbol) :
  - USDCHF  : n=57, WR 10.5%, avg -5.92 pips  (le pire, doit etre ecrase)
  - USDCAD  : n=10, WR  0.0%, avg -9.38 pips  (blacklist historique)
  - EURUSD  : n=43, WR 16.3%, avg -4.69 pips  (fragile, ECB = choc)
  - AUDUSD  : n=56, WR 28.6%, avg -3.53 pips  (fragile)
  - USDJPY  : n= 7, WR 42.9%, avg -0.16 pips  (peu de data, safe)
  - GBPUSD  : n=164,WR 63.4%, avg -0.26 pips  (le plus resilient)
  - XAUUSD  : n=0  (non capture par le screener actuel) → fallback

En news (wide_spread >= 2.0, 60j) :
  - USDCAD  : n=9,  WR 0%,  avg -9.38 pips
  - USDCHF  : n=57, WR 10.5%, avg -5.92 pips
  - AUDUSD  : n=56, WR 28.6%, avg -3.53 pips

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
NEWS_HEAT_MAP_ENV = "V9_NEWS_HEAT_MAP_ENABLED"

# ── News types reconnus ──────────────────────────────────────────────
NEWS_TYPE_NFP = "NFP"          # Non-Farm Payrolls (US, 1er vendredi du mois)
NEWS_TYPE_CPI = "CPI"          # Consumer Price Index (US, mensuel)
NEWS_TYPE_FOMC = "FOMC"        # Federal Reserve taux (US, 8x/an)
NEWS_TYPE_ECB = "ECB"          # European Central Bank taux (UE, 8x/an)
NEWS_TYPES_VALID = frozenset({NEWS_TYPE_NFP, NEWS_TYPE_CPI, NEWS_TYPE_FOMC, NEWS_TYPE_ECB})

# ── Symbols reconnus (cf. univers confirme CEO sprint V5) ────────────
SYMBOL_EURUSD = "EURUSD"
SYMBOL_USDJPY = "USDJPY"
SYMBOL_XAUUSD = "XAUUSD"
SYMBOL_GBPUSD = "GBPUSD"
SYMBOL_AUDUSD = "AUDUSD"

# ── Heat map (symbol, news_type) -> base_multiplier [0.0, 1.0] ───────
# Source : audit SQL live 03/08 (R14). Les paires blacklistees
# historiquement (USDCHF, USDCAD) heritent du multiplicateur 0.0
# (cf. v9_risk_parity.py Phase Hermes2). GBPUSD est la plus
# resiliente donc multiplicateur eleve.
#
# Logique de construction :
#   0.0 = blacklist totale (ne pas trader en news)
#   0.1-0.3 = danger (sizing tres reduit)
#   0.4-0.6 = prudent (sizing divise par 2)
#   0.7-0.9 = raisonnable (sizing legerement reduit)
#   1.0 = pas d'impact
HEAT_MAP: dict[tuple[str, str], float] = {
    # USDCHF - le pire, blacklist sur news US directes
    ("USDCHF", NEWS_TYPE_NFP):   0.0,
    ("USDCHF", NEWS_TYPE_CPI):   0.0,
    ("USDCHF", NEWS_TYPE_FOMC):  0.0,
    ("USDCHF", NEWS_TYPE_ECB):   0.5,
    # USDCAD - blacklist historique (cf. v9_risk_parity.py)
    ("USDCAD", NEWS_TYPE_NFP):   0.0,
    ("USDCAD", NEWS_TYPE_CPI):   0.0,
    ("USDCAD", NEWS_TYPE_FOMC):  0.0,
    ("USDCAD", NEWS_TYPE_ECB):   0.5,
    # EURUSD - fragile, ECB = choc direct
    ("EURUSD", NEWS_TYPE_NFP):   0.2,
    ("EURUSD", NEWS_TYPE_CPI):   0.3,
    ("EURUSD", NEWS_TYPE_FOMC):  0.3,
    ("EURUSD", NEWS_TYPE_ECB):   0.1,
    # AUDUSD - fragile, sensible aux news US
    ("AUDUSD", NEWS_TYPE_NFP):   0.3,
    ("AUDUSD", NEWS_TYPE_CPI):   0.4,
    ("AUDUSD", NEWS_TYPE_FOMC):  0.3,
    ("AUDUSD", NEWS_TYPE_ECB):   0.5,
    # USDJPY - safe overall, sensible au FOMC
    ("USDJPY", NEWS_TYPE_NFP):   0.5,
    ("USDJPY", NEWS_TYPE_CPI):   0.5,
    ("USDJPY", NEWS_TYPE_FOMC):  0.4,
    ("USDJPY", NEWS_TYPE_ECB):   0.6,
    # GBPUSD - la plus resiliente historiquement
    ("GBPUSD", NEWS_TYPE_NFP):   0.6,
    ("GBPUSD", NEWS_TYPE_CPI):   0.7,
    ("GBPUSD", NEWS_TYPE_FOMC):  0.5,
    ("GBPUSD", NEWS_TYPE_ECB):   0.7,
    # XAUUSD - pas de data live, proxy conservateur (or sensible FOMC/CPI)
    ("XAUUSD", NEWS_TYPE_NFP):   0.7,
    ("XAUUSD", NEWS_TYPE_CPI):   0.5,
    ("XAUUSD", NEWS_TYPE_FOMC):  0.6,
    ("XAUUSD", NEWS_TYPE_ECB):   0.7,
}

# Fallback par defaut (paire ou news_type inconnu) : sizing prudent
DEFAULT_BASE_MULTIPLIER = 0.8


# ── Kill switch accesseur (defaut OFF) ───────────────────────────────
def news_heat_map_enabled() -> bool:
    """Kill switch V9_NEWS_HEAT_MAP_ENABLED — Phase 143.

    Active la heat map news x paire (NFP / CPI / FOMC / ECB x
    EURUSD / USDJPY / XAUUSD / GBPUSD / AUDUSD). Defaut OFF
    (R25' strict motion CEO). Additif (R2), R6 fail-open.
    Module : core/v9/v9_news_heat_map.py (NEW, ZCode3 C2).
    """
    return ks_get(NEWS_HEAT_MAP_ENV, "0") == "1"


# ── Dataclass resultat ──────────────────────────────────────────────
@dataclass
class NewsHeatVerdict:
    """Verdict heat map pour (symbol, news_type, minutes_to_news)."""
    symbol: str = ""
    news_type: str = ""
    minutes_to_news: int = 0
    base_multiplier: float = 1.0
    minutes_factor: float = 1.0
    final_multiplier: float = 1.0
    phase_label: str = "normal"
    enabled: bool = False
    fallback_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "news_type": self.news_type,
            "minutes_to_news": self.minutes_to_news,
            "base_multiplier": round(self.base_multiplier, 3),
            "minutes_factor": round(self.minutes_factor, 3),
            "final_multiplier": round(self.final_multiplier, 3),
            "phase_label": self.phase_label,
            "enabled": self.enabled,
            "fallback_used": self.fallback_used,
        }


# ── Helpers internes (R18 code pur) ─────────────────────────────────
def _safe_str(s: Any, default: str = "") -> str:
    """Conversion str safe (R6 fail-open)."""
    if s is None:
        return default
    try:
        return str(s).strip().upper()
    except Exception:
        return default


def _is_valid_input(symbol: Any, news_type: Any, minutes_to_news: Any) -> bool:
    """Valide que les entrees sont exploitables (R6 fail-open).

    Retourne False si l'une des entrees est manifestement invalide
    (None, str non convertible en int pour minutes_to_news, type
    incompatible). Le verdict sera 1.0 dans ce cas (pass-through safe).
    """
    if symbol is None or news_type is None or minutes_to_news is None:
        return False
    # minutes_to_news doit etre numerique (int / float / str convertible).
    if isinstance(minutes_to_news, str):
        try:
            float(minutes_to_news)
        except (TypeError, ValueError):
            return False
    elif not isinstance(minutes_to_news, (int, float)):
        return False
    return True


def _safe_int(n: Any, default: int = 0) -> int:
    """Conversion int safe (R6 fail-open)."""
    if n is None:
        return default
    try:
        return int(n)
    except (TypeError, ValueError):
        try:
            return int(float(n))
        except Exception:
            return default


def _lookup_base_multiplier(symbol: str, news_type: str) -> tuple[float, bool]:
    """Retourne (base_multiplier, fallback_used).

    Si (symbol, news_type) absent de la heat map → fallback ×DEFAULT.
    Si news_type invalide → fallback ×DEFAULT (safe).
    """
    sym_u = _safe_str(symbol)
    nt_u = _safe_str(news_type)
    if nt_u not in NEWS_TYPES_VALID:
        return DEFAULT_BASE_MULTIPLIER, True
    val = HEAT_MAP.get((sym_u, nt_u))
    if val is None:
        return DEFAULT_BASE_MULTIPLIER, True
    return val, False


def _minutes_factor_from_window(minutes_to_news: int) -> tuple[float, str]:
    """Reimplemente la logique de fenetre du L19 attenuator.

    Note : on duplique la logique (pas d'import cyclique) pour rester
    autonome. Cf. v9_news_shock_attenuator.py pour la version
    canonique. Bornes identiques au L19.
      - 15 <= m <= 60 : 0.5 (pre_news)
      - 0  <= m < 15  : 0.0 (imminent / HALT)
      - -15 <= m < 0  : 0.5 (post_news)
      - -60 <= m < -15: 0.8 (normalisation)
      - autre         : 1.0 (normal, hors fenetre)
    """
    m = _safe_int(minutes_to_news)
    if 15 <= m <= 60:
        return 0.5, "pre_news"
    if 0 <= m < 15:
        return 0.0, "imminent"
    if -15 <= m < 0:
        return 0.5, "post_news"
    if -60 <= m < -15:
        return 0.8, "normalisation"
    return 1.0, "normal"


# ── API publique ────────────────────────────────────────────────────
def compute_news_heat_multiplier(
    symbol: str,
    news_type: str,
    minutes_to_news: int,
) -> float:
    """Multiplicateur final = base (heat) × minutes_factor (fenetre).

    Si kill switch OFF → 1.0 (pass-through, R25').
    Si symbol ou news_type inconnu → fallback ×DEFAULT (R6 safe).
    Si entree invalide → 1.0 (R6 fail-open).

    Args:
        symbol: paire (ex. 'EURUSD'). Insensible a la casse.
        news_type: type de news ('NFP' / 'CPI' / 'FOMC' / 'ECB').
        minutes_to_news: cf. L19. Positif = avant, negatif = apres.

    Returns:
        Multiplicateur final ∈ [0.0, 1.0].
    """
    if not news_heat_map_enabled():
        return 1.0  # pass-through (R25' defaut OFF)
    # R6 fail-open : entree invalide (None / str vide / type incompatible) -> 1.0
    if not _is_valid_input(symbol, news_type, minutes_to_news):
        return 1.0
    base, _ = _lookup_base_multiplier(symbol, news_type)
    minutes_factor, _ = _minutes_factor_from_window(minutes_to_news)
    # Composition : on prend le MIN des deux (plus restrictif gagne).
    # Justification : si la heat dit 0.0 (blacklist) ET qu'on est en
    # imminent (0.0), le resultat doit etre 0.0 (HALT). Si heat dit
    # 0.7 et imminent 0.0, c'est imminent qui gagne (0.0).
    final = min(base, minutes_factor)
    # R6 fail-open : clamp en [0.0, 1.0] pour eviter toute surprise.
    return max(0.0, min(1.0, final))


def classify_news_heat(
    symbol: str,
    news_type: str,
    minutes_to_news: int,
) -> NewsHeatVerdict:
    """Version dataclass de compute_news_heat_multiplier.

    Utile pour dashboard / tests. Meme regle MIN(base, minutes_factor).
    """
    enabled = news_heat_map_enabled()
    if not enabled:
        return NewsHeatVerdict(
            symbol=_safe_str(symbol),
            news_type=_safe_str(news_type),
            minutes_to_news=_safe_int(minutes_to_news),
            base_multiplier=1.0,
            minutes_factor=1.0,
            final_multiplier=1.0,
            phase_label="kill_switch_off",
            enabled=False,
            fallback_used=False,
        )
    base, fallback = _lookup_base_multiplier(symbol, news_type)
    minutes_factor, phase = _minutes_factor_from_window(minutes_to_news)
    final = max(0.0, min(1.0, min(base, minutes_factor)))
    return NewsHeatVerdict(
        symbol=_safe_str(symbol),
        news_type=_safe_str(news_type),
        minutes_to_news=_safe_int(minutes_to_news),
        base_multiplier=base,
        minutes_factor=minutes_factor,
        final_multiplier=final,
        phase_label=phase,
        enabled=True,
        fallback_used=fallback,
    )


def get_heat_map_snapshot() -> dict[str, dict[str, float]]:
    """Retourne un snapshot read-only de la heat map (pour dashboard).

    Format : {symbol: {news_type: multiplier}}.
    """
    out: dict[str, dict[str, float]] = {}
    for (sym, nt), val in HEAT_MAP.items():
        out.setdefault(sym, {})[nt] = round(val, 3)
    return out


def summarize_heat_verdicts(verdicts: list[NewsHeatVerdict]) -> dict:
    """Agregat d'une liste de verdicts (helper pour dashboard / tests).

    Retourne : n_total, n_kill_switch_off, n_enabled, n_fallback,
    n_halt (final=0), multiplier_avg, by_phase.
    """
    out = {
        "n_total": len(verdicts),
        "n_kill_switch_off": 0,
        "n_enabled": 0,
        "n_fallback": 0,
        "n_halt": 0,
        "multiplier_avg": 0.0,
        "by_phase": {},
    }
    if not verdicts:
        return out
    for v in verdicts:
        if not v.enabled:
            out["n_kill_switch_off"] += 1
        else:
            out["n_enabled"] += 1
            if v.fallback_used:
                out["n_fallback"] += 1
            if v.final_multiplier == 0.0:
                out["n_halt"] += 1
            ph = v.phase_label
            out["by_phase"][ph] = out["by_phase"].get(ph, 0) + 1
    out["multiplier_avg"] = round(
        sum(v.final_multiplier for v in verdicts) / len(verdicts), 3
    )
    return out
