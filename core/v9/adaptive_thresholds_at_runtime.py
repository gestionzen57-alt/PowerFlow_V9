"""adaptive_thresholds_at_runtime — Seuils dynamiques f(vol_regime, news_proximity).

Autopilot P3 CEO 2026-07-13 — chantier 8-12h d'effort estimé.

But : combler un des 6 écarts humain/V9 identifiés dans le diagnostic
stratégique senior. V9 a des seuils hard-coded (COALITION_THRESHOLD=5.38,
ANTAGONISM_THRESHOLD=31.39, PLIURE_THRESHOLD=1.7) qui ne s'adaptent pas à la
volatilité ambiante ni à la proximité d'un news macro. Un senior adapte
mentalement ses seuils : « aujourd'hui c'est EXTREME, je trade small ou
pas du tout ». V9 doit savoir faire pareil.

Ce module est **PUR** (pas de connexion DB), il reçoit un état de marché
et retourne des multiplicateurs à appliquer aux seuils baseline. Pattern
identique à vol_regime.py et zone_detector.py (skill
powerflow-v9-zone-detector) : testable sans DB, réutilisable hors pipeline.

Usage :
    from core.v9.adaptive_thresholds_at_runtime import (
        adaptive_multiplier_for_vol_regime, get_effective_thresholds,
        NEWS_SENSITIVITY_BY_TIMEFRAME,
    )

    mult = adaptive_multiplier_for_vol_regime("HIGH", news_phase="PRE_NEWS")
    # → 1.2 (HIGH × PRE_NEWS = 1.0 * 1.2 = 1.2)

    effective = get_effective_thresholds(vol_regime="EXTREME", news_phase="NEWS_SHOCK")
    # → {"COALITION": 5.38*1.5*1.5, "ANTAGONISM": 31.39*1.5*1.5, "PLIURE": 1.7*1.5*1.5}

Méthode (autopilot P3, 2026-07-13) :

Vol regime → multiplicateur (calibration empirique Phase 13.2 :
- LOW (calme) : aucune amplification — seuils baseline OK, le bruit est faible.
- NORMAL (P25..P75) : aucune amplification — zone de calibrage initiale.
- HIGH (P75..P95) : × 1.3 — élargit les seuils car les mouvements sont
  amplifiés par la vol ambiante, on veut moins de bruit dans les détections.
- EXTREME (≥P95) : × 1.5 — divise par 2 la sensibilité (vol × 1.5 = on
  détecte que les mouvements × 1.5 plus gros que la baseline).

News phase → multiplicateur (calibration à dire d'expert, à recalibrer
empiriquement post-livraison) :
- NORMAL/UNKNOWN : × 1.0 — pas d'impact.
- POST_NEWS : × 0.9 (légèrement resserré — on est post-shock, on peut être
  plus sélectif pour confirmer la direction).
- PRE_NEWS : × 1.3 — élargit, on ne sait pas ce qui va arriver.
- NEWS_SHOCK : × 1.5 — divise par 2 la sensibilité, comportement extrême.

Combiné : multiplicative (vol_multiplier * news_multiplier), borné [0.5, 2.0]
pour éviter les aberrations.

Per-timeframe override (optionnel) : M1 (× 1.5 stress typique scalp), M5 (× 1.2),
M15 et H1 (× 1.0 baseline), H4 et D1 (× 0.8 car longs horizons = calme).

Philosophie R25' : ce module **décrit** les seuils adaptés à l'état du
marché, ne les **applique pas automatiquement** (chaque patch sur les
constantes globales doit passer par DECISIONS_LOG). L'usage canonical
est : `Arbiter.consolidate()` lit le multiplicateur et l'enregistre dans
`consolidate()["adaptive_multiplier"]` pour traçabilité — Søn décide
ensuite s'il fige un recalibrage ou rollback.

Référence : DECISIONS_LOG §2026-07-13 « Série Autopilot CEO » §Action #3
(chantier P3 Adaptive Thresholds, premier livrable autopilot 2026-07-13).
"""
from __future__ import annotations

from typing import Literal

# ── Constantes de calibration empirique 2026-07-13 ──────────────────
# Vol regime → multiplicateur (l'élargissement des seuils en vol haute
# réduit le bruit de détection).
VOL_MULTIPLIER: dict[str, float] = {
    "LOW": 1.0,      # P25..baseline — calme, seuils baseline OK
    "NORMAL": 1.0,   # P25..P75 — zone de calibrage initiale
    "HIGH": 1.3,     # P75..P95 — vol amplifie, moins de bruit admissible
    "EXTREME": 1.5,  # ≥P95 — divise par 2 la sensibilité
}

# News phase → multiplicateur (PRÉ/POST/NEWS_SHOCK affectent la
# confiance sur l'interprétation du mouvement).
NEWS_MULTIPLIER: dict[str, float] = {
    "NORMAL": 1.0,
    "POST_NEWS": 0.9,
    "PRE_NEWS": 1.3,
    "NEWS_SHOCK": 1.5,
    "UNKNOWN": 1.0,
}

# Per-timeframe override (calibration à dire d'expert 2026-07-13).
TIMEFRAME_MULTIPLIER: dict[str, float] = {
    "M1": 1.5,
    "M5": 1.2,
    "M15": 1.0,
    "H1": 1.0,
    "H4": 0.8,
    "D1": 0.8,
}

# ── Per-session override (DIVERSIFY 2026-07-16, Gap 3) ──────────────
# La session porte une signature comportementale : l'Asie est un range
# calme (accumulation) où l'on veut des seuils plus SENSIBLES ; Londres et
# l'overlap sont volatils (breakout, confluence) où l'on veut des seuils
# plus EXIGEANTS pour filtrer le bruit. Jusqu'ici `session_marche` était
# calculé mais n'entrait dans aucun seuil (pur décor — cf. audit : 45 % des
# scènes en Asie, 98 % des trades en overlap). Ce multiplicateur branche
# enfin la session sur les seuils de détection.
# Vocabulaire aligné sur principle_engine._load_shared_context (session_map) :
# asie / london / new_york / overlap / sydney / inconnu.
SESSION_MULTIPLIER: dict[str, float] = {
    "asie": 0.8,       # range calme — seuils plus sensibles
    "sydney": 0.8,     # idem Asie (pré-Tokyo, faible volatilité)
    "london": 1.2,     # breakout, volume — seuils plus exigeants
    "new_york": 1.0,   # extension directionnelle — neutre
    "overlap": 1.3,    # confluence Londres/NY — le plus exigeant
    "inconnu": 1.0,    # dégradation gracieuse (R6) — aucun effet
}

# Bornes de sécurité — multiplicateur composite borné [0.5, 2.0]
# (évite les aberrations si le state machine produit un état non-mappé).
MIN_MULTIPLIER = 0.5
MAX_MULTIPLIER = 2.0

# Seuils baseline V9 (référence — alignés sur config.py).
BASELINE_THRESHOLDS: dict[str, float] = {
    "COALITION": 5.38,
    "ANTAGONISM": 31.39,
    "PLIURE": 1.7,
}

VolRegime = Literal["LOW", "NORMAL", "HIGH", "EXTREME"]
NewsPhase = Literal["NORMAL", "POST_NEWS", "PRE_NEWS", "NEWS_SHOCK", "UNKNOWN"]
Session = Literal["asie", "sydney", "london", "new_york", "overlap", "inconnu"]


# ── Helpers multiplicateurs ────────────────────────────────────


def adaptive_multiplier_for_vol_regime(
    vol_regime: str,
    *,
    news_phase: str = "UNKNOWN",
    timeframe: str | None = None,
    session: str | None = None,
) -> float:
    """Calcule le multiplicateur composite pour un état de marché donné.

    Args:
        vol_regime : "LOW" | "NORMAL" | "HIGH" | "EXTREME"
                     (défaut "NORMAL" si non reconnu — conservateur).
        news_phase : "NORMAL" | "POST_NEWS" | "PRE_NEWS" | "NEWS_SHOCK" | "UNKNOWN"
                     (défaut "UNKNOWN" → × 1.0).
        timeframe  : "M1"|"M5"|"M15"|"H1"|"H4"|"D1"|None (None = pas d'override).
        session    : "asie"|"sydney"|"london"|"new_york"|"overlap"|"inconnu"|None
                     (None ou non-mappé → × 1.0, dégradation gracieuse R6).

    Returns:
        float multiplicateur dans [0.5, 2.0]. 1.0 = aucune modification.

    Notes :
        - Si un état non-mappé est passé, fallback conservateur sur 1.0
          (cumulé avec un multiplier connu).
        - Combiné multiplicitif : vol * news * timeframe * session, puis borné.
        - KISS : pas de dépendance à la DB. Réactif au state machine uniquement.
    """
    vol_mult = VOL_MULTIPLIER.get(vol_regime, 1.0)
    news_mult = NEWS_MULTIPLIER.get(news_phase, 1.0)
    tf_mult = TIMEFRAME_MULTIPLIER.get(timeframe, 1.0) if timeframe else 1.0
    session_mult = SESSION_MULTIPLIER.get(session, 1.0) if session else 1.0

    composite = vol_mult * news_mult * tf_mult * session_mult

    # Bornage de sécurité (cf MIN_MULTIPLIER/MAX_MULTIPLIER)
    bounded = max(MIN_MULTIPLIER, min(MAX_MULTIPLIER, composite))
    return float(bounded)


def get_effective_thresholds(
    vol_regime: str = "NORMAL",
    *,
    news_phase: str = "UNKNOWN",
    timeframe: str | None = None,
    session: str | None = None,
    baseline: dict[str, float] | None = None,
) -> dict[str, float]:
    """Retourne les seuils baseline scalés par le multiplicateur composite.

    Args:
        vol_regime/news_phase/timeframe/session : cf `adaptive_multiplier_for_vol_regime`.
        baseline : seuils baseline optionnels (défaut = BASELINE_THRESHOLDS
                   du module, alignés sur config.py).

    Returns:
        dict {"COALITION": float, "ANTAGONISM": float, "PLIURE": float}.
        Les seuils sont arrondis à 2 décimales pour la lisibilité.

    Notes :
        - Le multiplicateur composite est appliqué **uniformément** aux
          3 seuils baseline. C'est la politique la plus simple (P3 initial).
          Une politique différenciée (e.g. COALITION × 1.5 mais ANTAGONISM × 1.0)
          reste possible par extension future (R22 — laisser pour après).
        - Si baseline=None, on utilise BASELINE_THRESHOLDS.
    """
    bl = baseline if baseline is not None else BASELINE_THRESHOLDS
    mult = adaptive_multiplier_for_vol_regime(
        vol_regime, news_phase=news_phase, timeframe=timeframe, session=session,
    )
    return {
        name: round(value * mult, 2)
        for name, value in bl.items()
    }


# ── Aliases d'API publique pour usage canonique ──────────────────

NEWS_SENSITIVITY_BY_TIMEFRAME = TIMEFRAME_MULTIPLIER  # pour import explicite
