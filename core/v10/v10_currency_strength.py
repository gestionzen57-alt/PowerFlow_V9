# ═══════════════════════════════════════════════════════════════════════════
# PowerFlow V10 — v10_currency_strength.py
# Module : Calcul force devises Fatman/Fatboy (Hawkeye reverse-engineered)
# Version : 1.0.0 — 2026-08-05
# Doctrine : R2 (additif pur), R7 (54 tests min), R9 (pas de skill auto)
#
# Logique Fatman :
#   1. Récupérer OHLCV des 7 paires majeures sur TF Fatman (= TF chart × mult)
#   2. Calculer retour % depuis ouverture du TF Fatman pour chaque devise
#   3. Neutraliser : soustraire la moyenne (sum des 8 scores = 0)
#   4. Normaliser 0-100 (50 = neutre)
#   5. Calculer sigma (convergence/divergence)
#   6. Identifier signal : forte × faible, gap institutionnel
#
# TF Fatman par TF chart (inclus M30) :
#   M1  → M5    M5  → M15   M15 → H1
#   M30 → H1    H1  → H4    H4  → D1
# ═══════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


# ── Constants ──────────────────────────────────────────────────────────────

CURRENCIES = ["USD", "EUR", "GBP", "AUD", "NZD", "JPY", "CHF", "CAD"]

# Paires directes (USD en dénominateur = quote)
DIRECT_PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"]
# Paires inversées (USD en numérateur = base)
INVERSE_PAIRS = ["USDJPY", "USDCHF", "USDCAD"]

# Map paire → (base, quote)
PAIR_CURRENCIES: Dict[str, Tuple[str, str]] = {
    "EURUSD": ("EUR", "USD"),
    "GBPUSD": ("GBP", "USD"),
    "AUDUSD": ("AUD", "USD"),
    "NZDUSD": ("NZD", "USD"),
    "USDJPY": ("USD", "JPY"),
    "USDCHF": ("USD", "CHF"),
    "USDCAD": ("USD", "CAD"),
}

# TF chart → TF Fatman (incluant M30)
FATMAN_TF_MAP: Dict[str, str] = {
    "M1":  "M5",
    "M5":  "M15",
    "M15": "H1",
    "M30": "H1",  # M30 → H1 (Fatboy principle : TF supérieur immédiat)
    "H1":  "H4",
    "H4":  "D1",
    "D1":  "W1",
    "W1":  "MN",
}

# Seuils de signal
GAP_STANDARD    = 35.0   # Seuil signal standard (score fort - score faible)
GAP_INSTITUTION = 48.0   # Seuil signal institutionnel
SIGMA_CONVERGENCE = 12.0  # σ < 12 → tendance forte (Fatboy)
SIGMA_DIVERGENCE  = 28.0  # σ > 28 → retournement potentiel

# Safe havens (Fatboy : filtre risk-off)
SAFE_HAVEN_CURRENCIES = {"JPY", "CHF"}

# Couleurs officielles Hawkeye
HAWKEYE_COLORS: Dict[str, str] = {
    "USD": "#00FFFF",  # Aqua
    "EUR": "#008000",  # Green
    "GBP": "#FFA500",  # Orange
    "AUD": "#FF0000",  # Red
    "CAD": "#FFFF00",  # Yellow
    "NZD": "#0000FF",  # Blue
    "JPY": "#FF00FF",  # Fuchsia
    "CHF": "#FFFFFF",  # White
}


# ── Enums & Dataclasses ────────────────────────────────────────────────────

class SignalType(Enum):
    NONE         = "NONE"
    STANDARD     = "STANDARD"       # Gap >= GAP_STANDARD
    INSTITUTIONAL = "INSTITUTIONAL" # Gap >= GAP_INSTITUTION


class MarketRegime(Enum):
    TRENDING     = "TRENDING"       # σ < SIGMA_CONVERGENCE
    NEUTRAL      = "NEUTRAL"
    DIVERGING    = "DIVERGING"      # σ > SIGMA_DIVERGENCE → retournement


@dataclass
class CurrencyBar:
    """OHLCV minimal pour un TF Fatman."""
    symbol: str
    open:   float
    high:   float
    low:    float
    close:  float
    volume: float = 0.0


@dataclass
class CurrencyScore:
    """Score brut et normalisé pour une devise."""
    currency:     str
    raw_return:   float   # Retour % depuis ouverture TF Fatman
    neutral_ret:  float   # Retour neutralisé (soustrait moyenne)
    score:        float   # Score normalisé 0-100 (50 = neutre)

    @property
    def is_strong(self) -> bool:
        return self.score >= 50 + GAP_STANDARD / 2

    @property
    def is_weak(self) -> bool:
        return self.score <= 50 - GAP_STANDARD / 2

    @property
    def is_extreme_strong(self) -> bool:
        return self.score >= 78.0

    @property
    def is_extreme_weak(self) -> bool:
        return self.score <= 22.0


@dataclass
class FatmanSignal:
    """
    Signal généré par FatmanCalculator.
    Contient les scores de toutes les devises + indicateurs de confluence.
    """
    tf_chart:         str
    tf_fatman:        str
    scores:           Dict[str, CurrencyScore] = field(default_factory=dict)
    sigma:            float = 0.0
    gap:              float = 0.0
    signal_type:      SignalType   = SignalType.NONE
    regime:           MarketRegime = MarketRegime.NEUTRAL
    dominant_strong:  Optional[str] = None
    dominant_weak:    Optional[str] = None
    safe_haven_active: bool = False
    notes:            List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tf_chart":         self.tf_chart,
            "tf_fatman":        self.tf_fatman,
            "scores":           {k: {"score": v.score, "raw_return": v.raw_return}
                                  for k, v in self.scores.items()},
            "sigma":            round(self.sigma, 4),
            "gap":              round(self.gap, 4),
            "signal_type":      self.signal_type.value,
            "regime":           self.regime.value,
            "dominant_strong":  self.dominant_strong,
            "dominant_weak":    self.dominant_weak,
            "safe_haven_active": self.safe_haven_active,
            "notes":            self.notes,
        }


@dataclass
class MultiTFResult:
    """
    Résultat de l'analyse multi-TF.
    Agrège les signaux de 2-4 TF pour confluence.
    """
    signals:          Dict[str, FatmanSignal] = field(default_factory=dict)
    best_tf:          Optional[str] = None
    best_pair:        Optional[str] = None   # Ex: "GBPJPY"
    confidence:       float = 0.0            # 0-100
    dominant_strong:  Optional[str] = None
    dominant_weak:    Optional[str] = None
    tf_confluence:    int = 0                # Nombre de TF en accord

    def to_dict(self) -> dict:
        return {
            "signals":         {k: v.to_dict() for k, v in self.signals.items()},
            "best_tf":         self.best_tf,
            "best_pair":       self.best_pair,
            "confidence":      round(self.confidence, 2),
            "dominant_strong": self.dominant_strong,
            "dominant_weak":   self.dominant_weak,
            "tf_confluence":   self.tf_confluence,
        }


# ── Core Calculator ────────────────────────────────────────────────────────

class FatmanCalculator:
    """
    Calcule les scores de force devises selon la logique Hawkeye Fatman.

    Usage :
        calc = FatmanCalculator(data_provider)
        signal = calc.compute("GBPUSD", tf_chart="M30")
        multi  = calc.compute_multi_tf(["M15", "M30", "H1", "H4"])
    """

    def __init__(self, data_provider=None):
        """
        data_provider : objet avec méthode :
            get_ohlcv(symbol: str, tf: str, bars: int) -> List[CurrencyBar]
        Si None, utiliser inject_bars() pour test.
        """
        self._provider = data_provider
        self._injected: Dict[str, List[CurrencyBar]] = {}

    # ── Injection de données (tests / backtest) ─────────────────────────

    def inject_bars(self, symbol: str, bars: List[CurrencyBar]) -> None:
        """Injecter des données mock pour tests."""
        self._injected[symbol.upper()] = bars

    def _get_bars(self, symbol: str, tf: str, n: int = 2) -> List[CurrencyBar]:
        key = symbol.upper()
        if key in self._injected:
            return self._injected[key][-n:]
        if self._provider is not None:
            return self._provider.get_ohlcv(symbol, tf, n)
        raise ValueError(f"Pas de données pour {symbol} TF={tf}. Injecter via inject_bars().")

    # ── TF Fatman ────────────────────────────────────────────────────────

    @staticmethod
    def get_fatman_tf(tf_chart: str) -> str:
        """Retourne le TF Fatman correspondant au TF chart."""
        tf = tf_chart.upper()
        if tf not in FATMAN_TF_MAP:
            raise ValueError(f"TF non supporté: {tf}. Supportés: {list(FATMAN_TF_MAP.keys())}")
        return FATMAN_TF_MAP[tf]

    # ── Calcul retour devise ─────────────────────────────────────────────

    @staticmethod
    def _pair_return(bar: CurrencyBar, is_direct: bool) -> float:
        """
        Retour % depuis ouverture du TF Fatman.
        Paire directe  (EURUSD) : (close - open) / open
        Paire inversée (USDJPY) : (open - close) / close  [vue depuis USD]
        """
        if bar.open == 0:
            return 0.0
        if is_direct:
            return (bar.close - bar.open) / bar.open
        else:
            # USD = base → force USD si close < open (paire monte = USD faible)
            return (bar.open - bar.close) / bar.close if bar.close != 0 else 0.0

    def _compute_raw_returns(self, tf_fatman: str) -> Dict[str, float]:
        """
        Calcule les retours bruts pour les 8 devises.
        USD = 0.0 (base de référence avant neutralisation)
        """
        returns: Dict[str, float] = {"USD": 0.0}

        # Paires directes : EUR, GBP, AUD, NZD
        for pair in DIRECT_PAIRS:
            base, _ = PAIR_CURRENCIES[pair]
            bars = self._get_bars(pair, tf_fatman, 2)
            bar  = bars[-1]  # Bougie courante
            returns[base] = self._pair_return(bar, is_direct=True)

        # Paires inversées : JPY, CHF, CAD (USD = base)
        for pair in INVERSE_PAIRS:
            _, quote = PAIR_CURRENCIES[pair]
            bars = self._get_bars(pair, tf_fatman, 2)
            bar  = bars[-1]
            # _pair_return(is_direct=False) = retour de la devise QUOTE (JPY/CHF/CAD)
            # ex. USDJPY monte → quote JPY se déprécie → raw < 0 (JPY faible ✅)
            raw = self._pair_return(bar, is_direct=False)
            # La quote suit son propre retour ; USD = inverse de la quote
            returns[quote] = raw
            returns["USD"] -= raw

        # Moyenner la contribution USD des 3 paires inversées
        returns["USD"] /= 3.0

        return returns

    # ── Neutralisation et normalisation ─────────────────────────────────

    @staticmethod
    def _neutralize(returns: Dict[str, float]) -> Dict[str, float]:
        """Soustrait la moyenne → somme des retours neutralisés = 0."""
        avg = sum(returns.values()) / len(returns)
        return {ccy: ret - avg for ccy, ret in returns.items()}

    @staticmethod
    def _normalize(neutral: Dict[str, float]) -> Dict[str, float]:
        """
        Normalise 0-100 avec 50 = neutre.
        max_abs définit l'amplitude max.
        """
        max_abs = max(abs(v) for v in neutral.values())
        if max_abs < 1e-12:
            return {ccy: 50.0 for ccy in neutral}
        return {ccy: 50.0 + (v / max_abs) * 50.0 for ccy, v in neutral.items()}

    # ── Sigma (Fatboy convergence) ────────────────────────────────────────

    @staticmethod
    def _compute_sigma(scores: Dict[str, float]) -> float:
        """Écart-type des 8 scores (mesure de dispersion = divergence inter-devises)."""
        vals  = list(scores.values())
        mean  = sum(vals) / len(vals)
        var   = sum((v - mean) ** 2 for v in vals) / len(vals)
        return math.sqrt(var)

    # ── Signal detection ─────────────────────────────────────────────────

    @staticmethod
    def _detect_signal(
        scores: Dict[str, CurrencyScore],
        sigma:  float,
    ) -> Tuple[SignalType, MarketRegime, Optional[str], Optional[str], float, bool, List[str]]:
        """
        Retourne (signal_type, regime, strong, weak, gap, safe_haven_active, notes).
        """
        sorted_scores = sorted(scores.values(), key=lambda s: s.score, reverse=True)
        strongest = sorted_scores[0]
        weakest   = sorted_scores[-1]
        gap       = strongest.score - weakest.score

        notes: List[str] = []

        # Régime de marché (Fatboy)
        if sigma < SIGMA_CONVERGENCE:
            regime = MarketRegime.TRENDING
            notes.append(f"Convergence forte σ={sigma:.1f} — ne pas contre-trader")
        elif sigma > SIGMA_DIVERGENCE:
            regime = MarketRegime.DIVERGING
            notes.append(f"Divergence σ={sigma:.1f} — retournement potentiel")
        else:
            regime = MarketRegime.NEUTRAL

        # Type de signal
        if gap >= GAP_INSTITUTION:
            sig_type = SignalType.INSTITUTIONAL
            notes.append(f"Signal INSTITUTIONNEL gap={gap:.1f}")
        elif gap >= GAP_STANDARD:
            sig_type = SignalType.STANDARD
            notes.append(f"Signal STANDARD gap={gap:.1f}")
        else:
            sig_type = SignalType.NONE

        # Safe haven flip (Fatboy)
        safe_haven_active = False
        top_2 = {sorted_scores[0].currency, sorted_scores[1].currency}
        if top_2 & SAFE_HAVEN_CURRENCIES == SAFE_HAVEN_CURRENCIES:
            safe_haven_active = True
            notes.append("SAFE HAVEN FLIP — JPY+CHF dominants → Risk-Off confirmé")
        elif top_2 & SAFE_HAVEN_CURRENCIES:
            safe_haven_active = True
            notes.append(f"Safe haven partiel — {top_2 & SAFE_HAVEN_CURRENCIES} dans top 2")

        dominant_strong = strongest.currency if sig_type != SignalType.NONE else None
        dominant_weak   = weakest.currency   if sig_type != SignalType.NONE else None

        return sig_type, regime, dominant_strong, dominant_weak, gap, safe_haven_active, notes

    # ── Interface principale ──────────────────────────────────────────────

    def compute(self, pair: str, tf_chart: str) -> FatmanSignal:
        """
        Calcule le signal Fatman pour un TF chart donné.

        Args:
            pair     : Paire de référence (ex: "GBPUSD") — pour info seulement
            tf_chart : TF du graphique de trading (M1, M5, M15, M30, H1, H4, D1)

        Returns:
            FatmanSignal avec tous les scores et le signal détecté.
        """
        tf_fatman = self.get_fatman_tf(tf_chart)

        # 1. Retours bruts
        raw_returns = self._compute_raw_returns(tf_fatman)

        # 2. Neutralisation
        neutral = self._neutralize(raw_returns)

        # 3. Normalisation 0-100
        normalized = self._normalize(neutral)

        # 4. Construire CurrencyScore objects
        scores: Dict[str, CurrencyScore] = {}
        for ccy in CURRENCIES:
            scores[ccy] = CurrencyScore(
                currency    = ccy,
                raw_return  = raw_returns.get(ccy, 0.0),
                neutral_ret = neutral.get(ccy, 0.0),
                score       = normalized.get(ccy, 50.0),
            )

        # 5. Sigma
        score_vals = {ccy: s.score for ccy, s in scores.items()}
        sigma = self._compute_sigma(score_vals)

        # 6. Signal detection
        sig_type, regime, strong, weak, gap, sh_active, notes = \
            self._detect_signal(scores, sigma)

        return FatmanSignal(
            tf_chart         = tf_chart,
            tf_fatman        = tf_fatman,
            scores           = scores,
            sigma            = sigma,
            gap              = gap,
            signal_type      = sig_type,
            regime           = regime,
            dominant_strong  = strong,
            dominant_weak    = weak,
            safe_haven_active = sh_active,
            notes            = notes,
        )

    def compute_multi_tf(
        self,
        tf_charts: List[str],
        pair: str = "EURUSD",
    ) -> MultiTFResult:
        """
        Calcule les signaux sur plusieurs TF et évalue la confluence.

        Grille V10 recommandée : ["M15", "M30", "H1", "H4"]
        """
        result = MultiTFResult()
        strong_counts: Dict[str, int] = {}
        weak_counts:   Dict[str, int] = {}

        for tf in tf_charts:
            try:
                sig = self.compute(pair, tf)
                result.signals[tf] = sig
                if sig.dominant_strong:
                    strong_counts[sig.dominant_strong] = \
                        strong_counts.get(sig.dominant_strong, 0) + 1
                if sig.dominant_weak:
                    weak_counts[sig.dominant_weak] = \
                        weak_counts.get(sig.dominant_weak, 0) + 1
            except Exception as e:
                # En mode test, certaines paires peuvent manquer
                result.signals[tf] = FatmanSignal(
                    tf_chart=tf,
                    tf_fatman=FATMAN_TF_MAP.get(tf, "?"),
                    notes=[f"Erreur: {e}"]
                )

        # Confluence : devise dominante sur le plus de TF
        if strong_counts:
            result.dominant_strong = max(strong_counts, key=strong_counts.get)
            result.tf_confluence   = strong_counts[result.dominant_strong]
        if weak_counts:
            result.dominant_weak = max(weak_counts, key=weak_counts.get)

        # Best TF = celui avec le plus grand gap et signal non-NONE
        best_gap = 0.0
        for tf, sig in result.signals.items():
            if sig.signal_type != SignalType.NONE and sig.gap > best_gap:
                best_gap      = sig.gap
                result.best_tf = tf

        # Best pair = forte × faible
        if result.dominant_strong and result.dominant_weak:
            result.best_pair = f"{result.dominant_strong}{result.dominant_weak}"

        # Confidence : 0-100 basé sur confluence et gap
        if result.tf_confluence > 0 and best_gap > 0:
            conf_base = min(100.0, (best_gap / GAP_INSTITUTION) * 60)
            conf_conf = min(40.0, result.tf_confluence * (40 / len(tf_charts)))
            result.confidence = conf_base + conf_conf

        return result


# ═══════════════════════════════════════════════════════════════════════
# RÉ-EXPORT COMPATIBILITÉ (réparation 2026-08-05)
# Le moteur legacy (CurrencyStrength / compute_currency_strength /
# V10CurrencyStrength / API Phase 23) a été déplacé dans
# v10_currency_strength_legacy.py pour préserver les 21 tests + 2
# scripts + 2 modules core qui l'importent (R2 additif pur — aucun
# travail supprimé). Le nouveau moteur FatmanCalculator reste maître
# ici.
# ═══════════════════════════════════════════════════════════════════════
try:  # import package normal
    from .v10_currency_pairs import (  # noqa: E402,F401
        INVERSION_MAP,
        PAIRS_USD,
        PAIRS_BY_CURRENCY,
    )
    from .v10_currency_strength_legacy import (  # noqa: E402,F401
        CurrencyStrength,
        compute_currency_strength,
        V10CurrencyStrength,
        compute_scores_from_db,
        DEFAULTS,
        WINDOW_BARS_BY_TF,
        API_DEFAULTS,
        FATMAN_TF_MAP as LEGACY_FATMAN_TF_MAP,
        _ema,
        _sma,
        _atr,
        _true_range,
        _percentile_rank,
        _momentum_normalized,
        _aggregate_currency,
    )
except ImportError:  # pragma: no cover — import top-level (tests/v10/)
    from v10_currency_pairs import (  # noqa: E402,F401
        INVERSION_MAP,
        PAIRS_USD,
        PAIRS_BY_CURRENCY,
    )
    from v10_currency_strength_legacy import (  # noqa: E402,F401
        CurrencyStrength,
        compute_currency_strength,
        V10CurrencyStrength,
        compute_scores_from_db,
        DEFAULTS,
        WINDOW_BARS_BY_TF,
        API_DEFAULTS,
        FATMAN_TF_MAP as LEGACY_FATMAN_TF_MAP,
        _ema,
        _sma,
        _atr,
        _true_range,
        _percentile_rank,
        _momentum_normalized,
        _aggregate_currency,
    )
