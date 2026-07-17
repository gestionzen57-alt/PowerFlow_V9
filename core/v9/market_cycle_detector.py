"""MarketCycleDetector — lecture du cycle de marché (Phase 13.3).

Le marché n'est pas aléatoire : il alterne entre des phases identifiables
qui ont chacune une signature comportementale propre :

    ACCUMULATION → CASSURE → TREND → DISTRIBUTION → CLIMAX → RETOUR → …

Jusqu'ici, la gestion du risque était aveugle à ce cycle : TP/SL identiques
pour toutes les phases. Ce module lit le cycle courant à partir des signaux
DÉJÀ produits par le pipeline cognitif V9 (aucun nouveau calcul de marché,
aucun LLM — R18) :

  - `scene.cinematique_json`     : vélocité, accélération, compression/extension
  - `scene.coalitions_json`      : intensité d'alignement, tendance, âge, stabilité
  - `scene.confluences_mtf_json` : profondeur MTF (D1/H4/…/M5), emboîtement
  - `regime.regime_type`         : PALIER/CASSURE/EXTENSION/RETOUR_EQUILIBRE/REJET
  - `behavior.phase`             : initiation/developpement/culmination/resolution
  - `behavior.point_de_rupture_detecte`

`MarketCycleDetector` fait deux choses :

  1. `extract(context)`  → normalise ces signaux hétérogènes en un
     `CycleSignals` stable et défensif (tout champ absent tombe sur un
     défaut neutre — R6, jamais bloquant).
  2. `detect(context, previous_phase)` → délègue la décision à
     `PhaseClassifier` (règles pures) et enrichit avec la transition
     détectée depuis la phase précédente.

Le détecteur ne persiste rien et ne décide d'aucun ordre : il décrit.
La calibration SL/TP qui en découle vit dans `dynamic_risk_manager.py`.

Doctrine :
  - R18 : code pur, aucun LLM.
  - R2  : couche additive — ne touche pas la chaîne cognitive existante.
  - R6  : défensif, tout signal manquant → défaut neutre, ne lève jamais.
"""
from __future__ import annotations

import enum
import json
from dataclasses import dataclass, field
from typing import Any

MARKET_CYCLE_VERSION = "1.0"

# Seuil de vélocité (|velocite_moyenne|) au-delà duquel on considère un
# climax (épuisement violent). Calibré empiriquement : sur 400 décisions
# récentes, médiane ≈ 0, p90 ≈ 0.014, p99 ≈ 1.17, max ≈ 2.72. Un climax est
# donc un événement rare de la queue de distribution.
CLIMAX_VELOCITY = 1.0

# Bornes d'intensité de coalition (échelle 0-100, cf `intensite_alignement`).
COALITION_STRONG = 60.0
COALITION_WEAK = 30.0

# Profondeurs MTF considérées « hautes » (espérance de vie longue) vs
# « basses » (éphémères). H1/M30 = neutre.
HTF_DEPTHS = frozenset({"D1", "H4"})
LTF_DEPTHS = frozenset({"M15", "M5", "M1"})


class MarketPhase(str, enum.Enum):
    """Phase du cycle de marché."""
    ACCUMULATION = "accumulation"   # Range, volatilité faible, coalitions naissantes
    CASSURE = "cassure"             # Breakout, volatilité qui explose
    TREND = "trend"                 # Mouvement directionnel, coalitions solides
    DISTRIBUTION = "distribution"   # Divergence, épuisement, coalitions qui se délitent
    CLIMAX = "climax"               # Extrême, vélocité max
    RETOUR = "retour"               # Mean reversion, retour à l'équilibre
    INDETERMINE = "indetermine"     # Signaux insuffisants → fallback


@dataclass
class CycleSignals:
    """Signaux normalisés extraits du contexte cognitif.

    Tous les champs ont un défaut neutre : un contexte partiel produit un
    `CycleSignals` exploitable plutôt qu'une exception (R6).
    """
    velocity_abs: float = 0.0
    acceleration: str = "stable"          # acceleration / stable / deceleration
    compression: str = "neutre"           # neutre / compression / extension
    angle: float = 0.0
    dispersion: float = 0.0
    regime_type: str = "NEUTRE"
    behavior_phase: str | None = None     # initiation/developpement/culmination/resolution
    behavior_intensite: str | None = None
    point_de_rupture: bool = False
    coalition_intensity: float = 0.0      # 0-100
    coalition_trend: str = "stable"       # montante / stable / declinante
    coalition_age: int = 0
    coalition_stability: float = 0.0      # 0-1
    mtf_depth: str | None = None          # D1/H4/H1/M30/M15/M5/M1
    mtf_score: float = 0.0
    mtf_emboitement: bool = False
    mean_reversion_zone: bool = False
    session: str | None = None
    # Diagnostic — nb de familles de signaux réellement présentes (0-4).
    signal_richness: int = 0

    @property
    def is_htf(self) -> bool:
        return self.mtf_depth in HTF_DEPTHS

    @property
    def is_ltf(self) -> bool:
        return self.mtf_depth in LTF_DEPTHS

    @property
    def coalition_class(self) -> str:
        """faible / moyenne / forte selon l'intensité d'alignement."""
        if self.coalition_intensity >= COALITION_STRONG:
            return "forte"
        if self.coalition_intensity < COALITION_WEAK:
            return "faible"
        return "moyenne"


@dataclass
class CycleState:
    """Résultat de `MarketCycleDetector.detect()`."""
    phase: MarketPhase
    confidence: float                     # 0-1
    signals: CycleSignals
    previous_phase: MarketPhase | None = None
    transition: str | None = None         # ex "accumulation→cassure"
    rationale: list[str] = field(default_factory=list)
    market_cycle_version: str = MARKET_CYCLE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "confidence": round(self.confidence, 3),
            "previous_phase": self.previous_phase.value if self.previous_phase else None,
            "transition": self.transition,
            "rationale": list(self.rationale),
            "coalition_class": self.signals.coalition_class,
            "mtf_depth": self.signals.mtf_depth,
            "regime_type": self.signals.regime_type,
            "behavior_phase": self.signals.behavior_phase,
            "velocity_abs": round(self.signals.velocity_abs, 5),
            "signal_richness": self.signals.signal_richness,
            "market_cycle_version": MARKET_CYCLE_VERSION,
        }


def _as_dict(value: Any) -> dict:
    """Coerce un champ *_json (dict OU str JSON) en dict. Défensif."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def _as_list(value: Any) -> list:
    """Coerce un champ *_json (list OU str JSON) en list. Défensif."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    return []


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


class MarketCycleDetector:
    """Détecte la phase du cycle de marché à partir du contexte cognitif."""

    def __init__(self) -> None:
        # Import paresseux pour éviter le cycle d'import avec phase_classifier
        # (qui importe MarketPhase/CycleSignals depuis ce module).
        from core.v9.phase_classifier import PhaseClassifier
        self._classifier = PhaseClassifier()

    # ── Extraction ────────────────────────────────────────────────

    def extract(self, context: dict | None) -> CycleSignals:
        """Normalise le contexte cognitif en `CycleSignals`.

        `context` peut être :
          - le `contexte_complet` décompressé (avec clés scene/behavior/regime)
          - un sous-arbre `scene` direct
          - un dict plat (tests unitaires)

        Tout champ absent → défaut neutre (R6).
        """
        # R6 — un contexte non-dict (None, str, list…) ne doit pas lever.
        context = context if isinstance(context, dict) else {}
        signals = CycleSignals()
        families_present = 0

        # scene : soit context["scene"], soit context lui-même (dict plat/tests)
        scene = _as_dict(context.get("scene")) or context

        # 1. Cinématique — vélocité, accélération, compression
        cin = _as_dict(scene.get("cinematique_json"))
        if cin:
            families_present += 1
            signals.velocity_abs = abs(_num(cin.get("velocite_moyenne")))
            signals.angle = _num(cin.get("angle"))
            signals.dispersion = _num(cin.get("dispersion_velocite"))
            accel = cin.get("acceleration_deceleration")
            if accel in ("acceleration", "stable", "deceleration"):
                signals.acceleration = accel
            comp = _as_dict(cin.get("compression_extension")).get("etat")
            if comp in ("neutre", "compression", "extension"):
                signals.compression = comp

        # 2. Coalitions — on retient la coalition dominante (première listée)
        coalitions = _as_list(scene.get("coalitions_json"))
        if coalitions:
            families_present += 1
            top = coalitions[0] if isinstance(coalitions[0], dict) else {}
            signals.coalition_intensity = _num(top.get("intensite_alignement"))
            trend = top.get("intensite_trend")
            if trend in ("montante", "stable", "declinante"):
                signals.coalition_trend = trend
            signals.coalition_age = int(_num(top.get("age_bars")))
            signals.coalition_stability = _num(top.get("stabilite"))

        # 3. Confluences MTF — profondeur, score, emboîtement
        mtf = _as_dict(scene.get("confluences_mtf_json"))
        if mtf:
            families_present += 1
            depth = mtf.get("coalition_mtf_depth")
            if isinstance(depth, str):
                signals.mtf_depth = depth
            signals.mtf_score = _num(mtf.get("coalition_mtf_score"))
            signals.mtf_emboitement = bool(mtf.get("emboitement_detecte"))

        # 4. Régime — via la clé "regime" (liste par devise) ou regime_type direct
        regime_type = context.get("regime_type") or scene.get("regime_type")
        regime_block = context.get("regime")
        if regime_type is None and regime_block is not None:
            regime_list = _as_list(regime_block)
            if regime_list and isinstance(regime_list[0], dict):
                regime_type = regime_list[0].get("regime_type")
                signals.mean_reversion_zone = bool(
                    regime_list[0].get("mean_reversion_zone")
                )
        if isinstance(regime_type, str):
            signals.regime_type = regime_type
            families_present += 1

        # 5. Behavior — phase, intensité, point de rupture
        behavior = _as_dict(context.get("behavior"))
        if behavior:
            bphase = behavior.get("phase")
            if isinstance(bphase, str):
                signals.behavior_phase = bphase
            binten = behavior.get("intensite")
            if isinstance(binten, str):
                signals.behavior_intensite = binten
            signals.point_de_rupture = bool(behavior.get("point_de_rupture_detecte"))

        # 6. Session — depuis contexte_temporel_json ou champ explicite
        temporel = _as_dict(scene.get("contexte_temporel_json"))
        session = (
            context.get("session_marche")
            or context.get("session")
            or _normalize_session(temporel.get("session"))
        )
        if isinstance(session, str):
            signals.session = session

        signals.signal_richness = families_present
        return signals

    # ── Détection ─────────────────────────────────────────────────

    def detect(
        self,
        context: dict | None,
        previous_phase: MarketPhase | str | None = None,
    ) -> CycleState:
        """Détecte la phase courante et la transition depuis `previous_phase`.

        Ne lève jamais (R6) : un contexte vide produit `INDETERMINE`.
        """
        signals = self.extract(context)
        phase, confidence, rationale = self._classifier.classify(signals)

        prev = _coerce_phase(previous_phase)
        transition = None
        if prev is not None and prev != phase:
            transition = f"{prev.value}→{phase.value}"

        return CycleState(
            phase=phase,
            confidence=confidence,
            signals=signals,
            previous_phase=prev,
            transition=transition,
            rationale=rationale,
        )


def _normalize_session(raw: Any) -> str | None:
    """Normalise le libellé de session FR (Londres/Asie/…) vers la clé
    interne (london/asie/…) utilisée par exit_simulator.DYNAMIC_PROFILES."""
    if not isinstance(raw, str):
        return None
    key = raw.strip().lower()
    mapping = {
        "asie": "asie", "asia": "asie",
        "londres": "london", "london": "london",
        "overlap": "overlap", "chevauchement": "overlap",
        "new york": "new_york", "new_york": "new_york", "newyork": "new_york",
        "after": "after", "after hours": "after", "apres": "after",
    }
    return mapping.get(key)


def _coerce_phase(value: MarketPhase | str | None) -> MarketPhase | None:
    if value is None:
        return None
    if isinstance(value, MarketPhase):
        return value
    try:
        return MarketPhase(str(value).lower())
    except ValueError:
        return None
