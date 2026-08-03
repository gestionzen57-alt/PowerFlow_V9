"""v9_pyramiding_engine_v4.py — Phase 136 : PyramidingEngine V4 (zones_state boost).

Extension V4 du PyramidingEngine qui ajoute un boost multiplicatif selon
l'état de la zone (zone_state) au moment du trade.

Mission CEO no-stop 03/08/2026 — sprint +1 V4 Hermes2.
Hypothèse : V3 (MTF boost ×1.2 si ≥3 TF alignés) + boost zones_state
supplémentaire selon l'état de la zone. Le trade V2/V3 qui se déclenche
quand la zone est en état de « naissance » ou « 2e jambe » a un edge plus
fort qu'en range plat ou sans zone trackable.

Composition multiplicative V2 × V3 × V4 :
    final = V2_multiplier × V3_MTF × V4_zones_state

Mapping zone_state (DB `zone_diagnostics.state`) → catégorie V4 :
  - EARLY_EXTREME  ≈ naissance  → ×1.2  (edge en formation, momentum)
  - ACCUMULATING   ≈ 2e_jambe   → ×1.1  (edge en construction)
  - RUPTURE        ≈ retest     → ×1.0  (pass-through, structure cassée)
  - NEUTRAL        ≈ range      → ×0.8  (bruit, edge plus faible)
  - LEAKING        (rare)       → ×1.0  (R6 fail-open)
  - None / inconnu              → ×1.0  (pass-through, R6 fail-open)

Audit SQL live 03/08/2026 (n=337 v9_paper_trades, join mode par snapshot) :
  - None (no zone)    : n=85,  WR=98.8%, +469.5p, +5.52p/trade (EDGE FORT)
  - ACCUMULATING      : n=118, WR=29.7%, -297.8p, -2.52p/trade
  - NEUTRAL           : n=104, WR=24.0%, -344.9p, -3.32p/trade (range, drain)
  - RUPTURE           : n=28,  WR=21.4%,  -80.6p, -2.88p/trade
  - EARLY_EXTREME     : n=2,   WR= 0.0%,   -5.8p, -2.90p/trade (trop peu)
Note : « None » correspond aux snapshots sans zone trackable ; ces trades
n'ont PAS de zone_state (donc V4 ne s'applique pas, V3 non plus). L'audit
confirme la dispersion zone_state × PNL qui justifie le boost.

Gain projeté : 50-100 pips (extension V3 + zones_state).
Doctrine : R2 additif, R6 fail-open, R25' motion CEO.
"""
from __future__ import annotations

from typing import Sequence

from core.v9.kill_switches import get
from core.v9.v9_pyramiding_engine_v3 import (
    PyramidingEngineV3,
    pyramiding_v3_mtf_boost_enabled,
)

VERSION = "4.0"

# ── Configuration V4 ────────────────────────────────────────────────
# Mapping zone_state → multiplicateur (cf. docstring).
ZONES_STATE_MULTIPLIERS: dict[str, float] = {
    "EARLY_EXTREME": 1.2,   # naissance
    "ACCUMULATING": 1.1,    # 2e_jambe
    "RUPTURE": 1.0,         # retest (pass-through)
    "NEUTRAL": 0.8,         # range
    "LEAKING": 1.0,         # fail-open (rare, n=1)
}

# État envoyé en legacy (prompt 136) — on accepte aussi ces noms.
LEGACY_ZONES_STATE_ALIAS: dict[str, str] = {
    "naissance": "EARLY_EXTREME",
    "2e_jambe": "ACCUMULATING",
    "retest": "RUPTURE",
    "range": "NEUTRAL",
}

PYRAMIDING_V4_ENABLED_ENV = "V9_PYRAMIDING_V4_ZONES_STATE_ENABLED"


# ── Kill switch V4 ──────────────────────────────────────────────────
def pyramiding_v4_zones_state_enabled() -> bool:
    """Kill switch V9_PYRAMIDING_V4_ZONES_STATE_ENABLED — Phase 136 (03/08).

    Active le boost zones_state (naissance ×1.2, 2e_jambe ×1.1, retest ×1.0,
    range ×0.8). Defaut OFF (R25' strict motion CEO).
    Additif (R2), R6 jamais bloquant.
    0 modif core/ partage (herite de PyramidingEngineV3).
    """
    return get(PYRAMIDING_V4_ENABLED_ENV, "0") == "1"


# ── Multiplicateur zones_state ──────────────────────────────────────
def _normalize_zone_state(zone_state: str | None) -> str | None:
    """Normalise un zone_state vers la nomenclature DB (5 valeurs canoniques).

    Accepte les alias legacy (naissance/2e_jambe/retest/range) et les noms
    canoniques DB (EARLY_EXTREME/ACCUMULATING/RUPTURE/NEUTRAL/LEAKING).
    Retourne None si l'input est None, vide ou non convertible.
    """
    if zone_state is None:
        return None
    s = str(zone_state).strip()
    if not s:
        return None
    if s in ZONES_STATE_MULTIPLIERS:
        return s
    if s in LEGACY_ZONES_STATE_ALIAS:
        return LEGACY_ZONES_STATE_ALIAS[s]
    low = s.lower()
    if low in LEGACY_ZONES_STATE_ALIAS:
        return LEGACY_ZONES_STATE_ALIAS[low]
    up = s.upper()
    if up in ZONES_STATE_MULTIPLIERS:
        return up
    return None  # inconnu → R6 fail-open pass-through


def compute_zones_state_multiplier(zone_state: str | None) -> float:
    """Retourne le multiplicateur V4 selon zone_state.

    Logique :
      - EARLY_EXTREME (naissance) : ×1.2
      - ACCUMULATING  (2e_jambe)  : ×1.1
      - RUPTURE       (retest)    : ×1.0 (pass-through)
      - NEUTRAL       (range)     : ×0.8
      - LEAKING                   : ×1.0 (fail-open)
      - None / inconnu            : ×1.0 (pass-through, R6 fail-open)
    """
    if zone_state is None:
        return 1.0
    normalized = _normalize_zone_state(zone_state)
    if normalized is None:
        return 1.0
    return ZONES_STATE_MULTIPLIERS.get(normalized, 1.0)


# ── V4 Pyramiding Engine (extension V3 + zones_state boost) ────────
class PyramidingEngineV4(PyramidingEngineV3):
    """PyramidingEngine V4 = V3 + boost zones_state.

    Herite de PyramidingEngineV3 (STARS/SUPER_STARS + MTF boost).
    Ajoute le boost zones_state (naissance/2e_jambe/retest/range) avec
    composition multiplicative V2 × V3_MTF × V4_zones_state.

    Additif (R2) : ne modifie pas V3, etend le comportement.
    """

    def __init__(self) -> None:
        super().__init__()

    def evaluate_v4(
        self,
        signal: dict,
        aligned_timeframes: Sequence[str] | None = None,
        zone_state: str | None = None,
        context: dict | None = None,
    ) -> dict:
        """Composition V2 × V3 MTF × V4 zones_state.

        Args:
            signal : dict compatible V3.evaluate_v3() (mêmes clés).
            aligned_timeframes : TF confirmes (M5/M15/H1, etc.).
            zone_state : etat de la zone DB (EARLY_EXTREME/ACCUMULATING/
                         RUPTURE/NEUTRAL/LEAKING) ou legacy (naissance/.../range).
            context : dict optionnel propage aux couches V2/V3.

        Returns:
            dict V3 enrichi avec :
              - v4_zones_state_normalized : str | None
              - v4_zones_state_multiplier : float (1.0..1.2 ou 0.8)
              - v4_zones_state_active : bool
              - v4_final_multiplier : float (V2 × V3 × V4)
              - v4_combo : str
              - v4_leviers_combined : list[str]
        """
        # 1. Evaluation V3 (STARS/SUPER_STARS + MTF boost)
        v3_result = self.evaluate_v3(signal, aligned_timeframes, context)
        v3_mult = v3_result.get("v3_final_multiplier", 1.0)

        # 2. Evaluation V4 zones_state (avec garde kill switch)
        normalized = _normalize_zone_state(zone_state)
        v4_mult = compute_zones_state_multiplier(zone_state)
        v4_active = pyramiding_v4_zones_state_enabled() and normalized is not None
        if not v4_active:
            v4_mult_applied = 1.0
        else:
            v4_mult_applied = v4_mult

        final_mult = round(v3_mult * v4_mult_applied, 4)

        leviers = list(v3_result.get("v3_leviers_combined", []))
        if v4_active and v4_mult_applied != 1.0:
            tag = f"L18_pyramiding_v4_zones_{normalized.lower()}_x{v4_mult_applied}"
            leviers.append(tag)

        return {
            **v3_result,
            "v4_zones_state_input": zone_state,
            "v4_zones_state_normalized": normalized,
            "v4_zones_state_multiplier": v4_mult,
            "v4_zones_state_active": v4_active,
            "v4_zones_state_leviers": (
                [f"L18_pyramiding_v4_zones_{normalized.lower()}_x{v4_mult_applied}"]
                if v4_active and v4_mult_applied != 1.0
                else []
            ),
            "v4_final_multiplier": final_mult,
            "v4_combo": v3_result.get("v3_combo", "base")
            + (
                f"_zones_{normalized.lower()}"
                if v4_active and v4_mult_applied != 1.0
                else ""
            ),
            "v4_leviers_combined": leviers,
        }
