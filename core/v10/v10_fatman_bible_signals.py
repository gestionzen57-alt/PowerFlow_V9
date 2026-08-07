"""V10 Fatman Bible Signals — 6 signaux + 6 filtres + 4 principes Fatboy.

Implémente §5-§7 du document `docs/strategy/FATMAN_BIBLE.md`.

Doctrine V10 : R2 additif pur (importe FatmanCalculator via tolerance
package/top-level), R6 fail-open (data absente → pas de signal), R7
tests verts, R8 seuils surchargeables, R9 audit JSON, R10 capital
protégé (le module n'exécute aucun ordre — il retourne uniquement
des décision dataclasses).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Tolerant imports (compat tests/v10/)
try:
    from .v10_currency_strength import (
        GAP_STANDARD,
        GAP_INSTITUTION,
        SIGMA_CONVERGENCE,
        SIGMA_DIVERGENCE,
        SAFE_HAVEN_CURRENCIES,
    )
except ImportError:  # pragma: no cover — tests/v10/
    from v10_currency_strength import (
        GAP_STANDARD,
        GAP_INSTITUTION,
        SIGMA_CONVERGENCE,
        SIGMA_DIVERGENCE,
        SAFE_HAVEN_CURRENCIES,
    )


# ─────────────────────────────────────────────────────────────────────
# Définitions des 6 signaux (FATMAN BIBLE §5)
# ─────────────────────────────────────────────────────────────────────
@dataclass
class BibleSignalResult:
    """Résultat d'un signal Fatman Bible."""
    signal_id: int = 0
    pair: str = ""
    direction: str = "NONE"     # LONG / SHORT
    confidence: float = 0.0     # 0-100
    gap: float = 0.0            # |forte - faible|
    sigma: float = 0.0
    is_institutional: bool = False
    is_safe_haven: bool = False
    is_aligned_mtf: bool = False
    wr_target: float = 0.0
    rr_target: float = 0.0
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict:
        return {
            "signal_id": self.signal_id,
            "pair": self.pair, "direction": self.direction,
            "confidence": round(self.confidence, 1),
            "gap": round(self.gap, 2), "sigma": round(self.sigma, 2),
            "is_institutional": self.is_institutional,
            "is_safe_haven": self.is_safe_haven,
            "is_aligned_mtf": self.is_aligned_mtf,
            "wr_target": self.wr_target, "rr_target": self.rr_target,
            "notes": list(self.notes),
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers (référencés par les 6 signaux)
# ─────────────────────────────────────────────────────────────────────
def _safe_sigma(direction_pos: float, direction_neg: float,
                all_scores: List[float]) -> float:
    """Sigma = écart-type des scores normalisés (Fatboy principle)."""
    if not all_scores or len(all_scores) < 2:
        return 0.0
    n = len(all_scores)
    m = sum(all_scores) / n
    var = sum((s - m) ** 2 for s in all_scores) / max(n - 1, 1)
    return math.sqrt(var)


def _pair_score(fatman_scores: Dict[str, float], pair: str) -> Tuple[float, str]:
    """Score composite d'une paire = score_base - score_quote (direction).

    Returns (delta, direction) où direction ∈ {"LONG_BASE", "SHORT_BASE", "NEUTRAL"}.
    """
    if len(pair) != 6:
        return 0.0, "NEUTRAL"
    base, quote = pair[:3], pair[3:]
    bs = fatman_scores.get(base, 50.0)
    qs = fatman_scores.get(quote, 50.0)
    delta = bs - qs  # sign = which currency is strong
    direction = "LONG_BASE" if delta > 0 else "SHORT_BASE" if delta < 0 else "NEUTRAL"
    return delta, direction


def _is_safe_haven_fatboy(fatman_scores: Dict[str, float], top_n: int = 3) -> bool:
    """Signal 4 BIBLE : JPY et CHF dans le top N des devises fortes."""
    if not fatman_scores:
        return False
    sorted_currencies = sorted(fatman_scores.items(),
                                key=lambda kv: kv[1], reverse=True)
    top = {c for c, _ in sorted_currencies[:top_n]}
    return "JPY" in top and "CHF" in top


def _is_mtf_aligned(fatman_m30: Dict[str, float],
                    fatman_h1: Dict[str, float], pair: str) -> bool:
    """Signal 6 BIBLE : M30 et H1 indiquent la même direction."""
    if len(pair) != 6 or not fatman_m30 or not fatman_h1:
        return False
    d_m30, _ = _pair_score(fatman_m30, pair)
    d_h1, _ = _pair_score(fatman_h1, pair)
    return (d_m30 > 0 and d_h1 > 0) or (d_m30 < 0 and d_h1 < 0)


# ─────────────────────────────────────────────────────────────────────
# Les 6 signaux (FATMAN BIBLE §5) — tous output un BibleSignalResult
# ─────────────────────────────────────────────────────────────────────
def signal_1_forte_faible(
    pair: str,
    fatman_scores: Dict[str, float],
    *,
    threshold: float = GAP_STANDARD,
    is_institutional_thr: float = GAP_INSTITUTION,
) -> Optional[BibleSignalResult]:
    """Signal 1 — FORTE × FAIBLE Standard (gap ≥ 35) / Institutionnel (≥ 48).

    WR ~62% (standard) / ~71% (institutionnel). R:R 1:1.5 / 1:2.5.
    """
    if len(pair) != 6 or not fatman_scores:
        return None
    delta, direction = _pair_score(fatman_scores, pair)
    gap = abs(delta)
    if gap < threshold:
        return None
    is_inst = gap >= is_institutional_thr
    sig = BibleSignalResult(
        signal_id=1, pair=pair,
        direction="LONG" if direction == "LONG_BASE" else "SHORT",
        confidence=min(100.0, gap),
        gap=gap, sigma=_safe_sigma(0, 0, list(fatman_scores.values())),
        is_institutional=is_inst,
        wr_target=71.0 if is_inst else 62.0,
        rr_target=2.5 if is_inst else 1.5,
    )
    sig.notes.append("FORTE x FAIBLE " + ("INSTITUTIONNEL" if is_inst
                                          else "STANDARD"))
    return sig


def signal_2_inst(
    pair: str,
    fatman_scores: Dict[str, float],
    *,
    threshold: float = GAP_INSTITUTION,
) -> Optional[BibleSignalResult]:
    """Signal 2 — FORTE × FAIBLE Institutionnel (priorité selon BIBLE).

    WR ~71%, R:R 1:2.5.
    """
    if len(pair) != 6:
        return None
    delta, direction = _pair_score(fatman_scores, pair)
    if abs(delta) < threshold:
        return None
    gap = abs(delta)
    sig = BibleSignalResult(
        signal_id=2, pair=pair,
        direction="LONG" if direction == "LONG_BASE" else "SHORT",
        confidence=gap, gap=gap,
        sigma=_safe_sigma(0, 0, list(fatman_scores.values())),
        is_institutional=True,
        wr_target=71.0, rr_target=2.5,
    )
    sig.notes.append("PRIORITY BIBLE §5 — high WR attendu")
    return sig


def signal_3_divergence(
    pair: str,
    fatman_scores: Dict[str, float],
    *,
    sigma_threshold: float = SIGMA_DIVERGENCE,
    gap_threshold: float = GAP_STANDARD,
) -> Optional[BibleSignalResult]:
    """Signal 3 — DIVERGENCE EXTRÊME (σ > 28 + gap ≥ 35).

    WR ~68%, R:R 1:2. Attention BIBLE : attendre confirmation bougie.
    """
    if len(pair) != 6 or not fatman_scores:
        return None
    sigma = _safe_sigma(0, 0, list(fatman_scores.values()))
    if sigma <= sigma_threshold:
        return None
    delta, direction = _pair_score(fatman_scores, pair)
    if abs(delta) < gap_threshold:
        return None
    gap = abs(delta)
    sig = BibleSignalResult(
        signal_id=3, pair=pair,
        direction="LONG" if direction == "LONG_BASE" else "SHORT",
        confidence=min(100.0, gap * (1 + sigma / 100.0)),
        gap=gap, sigma=sigma, is_institutional=gap >= GAP_INSTITUTION,
        wr_target=68.0, rr_target=2.0,
    )
    sig.notes.append("DIVERGENCE EXTREME — attendre confirmation bougie")
    return sig


def signal_4_safe_haven_flip(
    fatman_scores: Dict[str, float],
    *,
    pairs: Optional[List[str]] = None,
    top_n: int = 3,
) -> List[BibleSignalResult]:
    """Signal 4 — SAFE HAVEN FLIP (Fatboy : JPY et CHF dans top 3).

    Actions BIBLE : vendre les paires Risk-On (AUD, NZD contre USD/JPY/CHF).
    WR ~74%, R:R 1:2. Fréquence 2-3/mois.
    """
    if not _is_safe_haven_fatboy(fatman_scores, top_n=top_n):
        return []
    pairs = pairs or []
    risk_on_pairs = {"AUDUSD", "NZDUSD", "GBPJPY", "EURJPY"}
    safe_pairs = {"USDJPY", "USDCHF", "EURUSD", "GBPUSD"}
    out: List[BibleSignalResult] = []
    for pair in pairs:
        base, quote = pair[:3], pair[3:]
        in_risk_on = (base in {"AUD", "NZD"} and quote == "USD") \
            or (base in {"GBP", "EUR"} and quote == "JPY")
        in_safe = (base == "USD" and quote in {"JPY", "CHF"}) \
            or (base in {"EUR", "GBP"} and quote == "USD")
        delta, direction = _pair_score(fatman_scores, pair)
        if in_safe and delta > 0:
            # JPY/CHF faibles, AUD/NZD encore forts relative → small signal
            sig = BibleSignalResult(
                signal_id=4, pair=pair, direction="LONG", confidence=60.0,
                gap=abs(delta),
                sigma=_safe_sigma(0, 0, list(fatman_scores.values())),
                wr_target=74.0, rr_target=2.0, is_safe_haven=True,
            )
            sig.notes.append("SAFE HAVEN FLIP — vente risk-on")
            out.append(sig)
        elif in_risk_on and delta < 0:
            sig = BibleSignalResult(
                signal_id=4, pair=pair, direction="SHORT",
                confidence=60.0, gap=abs(delta),
                sigma=_safe_sigma(0, 0, list(fatman_scores.values())),
                wr_target=74.0, rr_target=2.0, is_safe_haven=True,
            )
            sig.notes.append("SAFE HAVEN FLIP — risk-on dégradé")
            out.append(sig)
    return out


def signal_5_convergence(
    pair: str,
    fatman_scores: Dict[str, float],
    *,
    sigma_threshold: float = SIGMA_CONVERGENCE,
) -> Optional[BibleSignalResult]:
    """Signal 5 — CONVERGENCE FORTE (σ < 12 + ordre cohérent).

    BIBLE : confirmation de position, PAS d'entrée seule.
    Renvoie None (utiliser compute_signal_5_convergence pour la validation).
    """
    if len(pair) != 6 or not fatman_scores:
        return None
    sigma = _safe_sigma(0, 0, list(fatman_scores.values()))
    if sigma >= sigma_threshold:
        return None
    sorted_currencies = sorted(fatman_scores.items(),
                                key=lambda kv: kv[1], reverse=True)
    # Ordre cohérent : la devise la plus forte a un score clairement dominant
    if len(sorted_currencies) < 2:
        return None
    top_score = sorted_currencies[0][1]
    second = sorted_currencies[1][1]
    if top_score - second < 15:  # pas assez dominant
        return None
    delta, direction = _pair_score(fatman_scores, pair)
    if direction == "NEUTRAL":
        return None
    sig = BibleSignalResult(
        signal_id=5, pair=pair,
        direction="LONG" if direction == "LONG_BASE" else "SHORT",
        confidence=top_score, gap=abs(delta),
        sigma=sigma, wr_target=0.0, rr_target=0.0,
    )
    sig.notes.append("CONVERGENCE FORTE — confirmer via S1 ou S2 (pas d'entrée seule)")
    return sig


def signal_6_continuation_mtf(
    pair: str,
    fatman_m30: Dict[str, float],
    fatman_h1: Dict[str, float],
) -> Optional[BibleSignalResult]:
    """Signal 6 — CONTINUATION M30 → H1 ALIGNÉ (même direction).

    WR ~69%, R:R 1:18.
    """
    if not _is_mtf_aligned(fatman_m30, fatman_h1, pair):
        return None
    # Take H1 (le TF supérieur), le momentum confirmé par M30
    delta, direction = _pair_score(fatman_h1, pair)
    if direction == "NEUTRAL":
        return None
    sig = BibleSignalResult(
        signal_id=6, pair=pair,
        direction="LONG" if direction == "LONG_BASE" else "SHORT",
        confidence=abs(delta), gap=abs(delta),
        sigma=_safe_sigma(0, 0, list(fatman_h1.values())),
        is_aligned_mtf=True,
        wr_target=69.0, rr_target=1.8,
    )
    sig.notes.append("M30 + H1 alignés — continuation")
    return sig


# ─────────────────────────────────────────────────────────────────────
# 6 filtres Edge Fund (FATMAN BIBLE §7)
# ─────────────────────────────────────────────────────────────────────
@dataclass
class BibleFilterResult:
    """Résultat d'un filtre Edge Fund Bible."""
    filter_id: str = ""
    name: str = ""
    passed: bool = False
    reason: str = ""

    def as_dict(self) -> Dict:
        return {"filter_id": self.filter_id, "name": self.name,
                "passed": self.passed, "reason": self.reason}


def filter_session(
    hour_utc: int,
    *,
    sessions: Optional[Dict[str, Tuple[int, int]]] = None,
) -> BibleFilterResult:
    """Filtre 1 — Sessions London (08-17 CET = 07-16 UTC) + NY (14-23 CET = 13-22 UTC)."""
    if sessions is None:
        sessions = {"LONDON": (7, 16), "NY": (13, 22)}
    in_london = sessions["LONDON"][0] <= hour_utc < sessions["LONDON"][1]
    in_ny = sessions["NY"][0] <= hour_utc < sessions["NY"][1]
    if in_london or in_ny:
        return BibleFilterResult("1", "session", True, "OK London/NY")
    return BibleFilterResult("1", "session", False,
                             f"Hour {hour_utc} hors London/NY")


def filter_atr_dynamics(
    atr_now: float,
    avg_atr_20d: float,
    *,
    atr_min_ratio: float = 0.7,
) -> BibleFilterResult:
    """Filtre 2 — ATR(14) > 70% de la moyenne 20j."""
    if avg_atr_20d <= 0 or atr_now <= 0:
        return BibleFilterResult("2", "atr_dynamics", False,
                                 "ATR invalide (≤0)")
    ratio = atr_now / avg_atr_20d
    if ratio >= atr_min_ratio:
        return BibleFilterResult("2", "atr_dynamics", True,
                                 f"ratio {ratio:.2f} >= {atr_min_ratio}")
    return BibleFilterResult("2", "atr_dynamics", False,
                             f"ratio {ratio:.2f} < {atr_min_ratio} (trop calme)")


def filter_spread(
    spread_now: float,
    spread_avg_daily: float,
    *,
    spread_max_ratio: float = 2.0,
) -> BibleFilterResult:
    """Filtre 3 — Spread < 2× spread moyen journalier."""
    if spread_avg_daily <= 0 or spread_now <= 0:
        return BibleFilterResult("3", "spread", False, "spread invalide")
    ratio = spread_now / spread_avg_daily
    if ratio < spread_max_ratio:
        return BibleFilterResult("3", "spread", True,
                                 f"ratio {ratio:.2f} < {spread_max_ratio}")
    return BibleFilterResult("3", "spread", False,
                             f"spread {ratio:.2f}×moy (anormal)")


def filter_correlation_with_open_positions(
    candidate_pair: str,
    corr_with_open: Dict[str, float],
    open_pairs: List[str],
    *,
    threshold: float = 0.7,
) -> BibleFilterResult:
    """Filtre 4 — Pas de 2 paires corrélées > 0.7 simultanément."""
    if not open_pairs or not corr_with_open:
        return BibleFilterResult("4", "correlation", True,
                                 "no open positions to correlate")
    for p in open_pairs:
        c = corr_with_open.get(p, 0.0)
        if abs(c) > threshold:
            return BibleFilterResult("4", "correlation", False,
                                     f"{p} corr={c:.2f} > {threshold}")
    return BibleFilterResult("4", "correlation", True, "OK")


def filter_news_window(
    minutes_to_news: Optional[int] = None,
    *,
    window_min: int = 30,
) -> BibleFilterResult:
    """Filtre 5 — Fenêtre ±30min autour des news impact HIGH.

    R6 : si inconnu (None) → fail-open, on suppose qu'il n'y a pas
    d'event immédiat (à câbler sur news_calendar live).
    """
    if minutes_to_news is None:
        return BibleFilterResult("5", "news_window", True,
                                 "no news data — fail-open (R6)")
    if 0 <= minutes_to_news <= window_min:
        return BibleFilterResult("5", "news_window", False,
                                 f"news dans {minutes_to_news}min "
                                 f"(fenêtre ±{window_min})")
    return BibleFilterResult("5", "news_window", True,
                             f"prochain news à {minutes_to_news}min")


def filter_sigma(
    sigma: float,
    *,
    sigma_max: float = 35.0,
) -> BibleFilterResult:
    """Filtre 6 — Pas d'entrée si σ > 35 (trop de bruit)."""
    if sigma <= 0:
        return BibleFilterResult("6", "sigma", False, "sigma invalide")
    if sigma <= sigma_max:
        return BibleFilterResult("6", "sigma", True,
                                 f"sigma={sigma:.2f} <= {sigma_max}")
    return BibleFilterResult("6", "sigma", False,
                             f"sigma={sigma:.2f} > {sigma_max} (trop de bruit)")


# ─────────────────────────────────────────────────────────────────────
# 4 principes Fatboy (FATMAN BIBLE §6) — helper de validation
# ─────────────────────────────────────────────────────────────────────
def principle_sigma_check(sigma: float) -> Tuple[bool, str]:
    """Principe 1 — Sigma convergence/divergence : σ < 12 (convergence)
    ou σ > 28 (divergence). Interdit entre 12-28 (zone grise)."""
    if sigma < SIGMA_CONVERGENCE:
        return True, "convergence forte"
    if sigma > SIGMA_DIVERGENCE:
        return True, "divergence extrême"
    return False, f"zone grise σ∈[{SIGMA_CONVERGENCE},{SIGMA_DIVERGENCE}]"


def principle_harmonie_tf(
    fatman_m30: Dict[str, float], fatman_h1: Dict[str, float], pair: str
) -> bool:
    """Principe 2 — Harmonies TF : signal multi-TF doit être aligné."""
    return _is_mtf_aligned(fatman_m30, fatman_h1, pair)


def principle_safe_haven_filter(
    fatman_scores: Dict[str, float], top_n: int = 3
) -> bool:
    """Principe 3 — Safe Haven filter : skip entrée risk-off si CHF/JPY
    dominent (déjà risk-off)."""
    return not _is_safe_haven_fatboy(fatman_scores, top_n=top_n)


def principle_volume_required(
    volume_signal: float,
    volume_avg: float,
    *,
    min_ratio: float = 0.8,
) -> bool:
    """Principe 4 — Pas de signal sans volume (volume_signal >= 80% avg)."""
    if volume_avg <= 0:
        return False
    return volume_signal / volume_avg >= min_ratio


# ─────────────────────────────────────────────────────────────────────
# FATBOY GATE — Option C Hybrid : meta-filter pour downgrade progressif
# ─────────────────────────────────────────────────────────────────────
@dataclass
class FatboyGateResult:
    """Résultat du gate Fatboy (3 principes)."""
    passed: bool                          # True si les 3 principes OK
    sigma_ok: bool
    harmonie_ok: bool
    safe_haven_ok: bool
    sigma_value: float
    harmonie_details: str
    safe_haven_details: str
    downgrade_reason: str = ""            # "sigma" | "harmonie" | "safe_haven" | ""

    def as_dict(self) -> Dict:
        return {
            "passed": self.passed,
            "sigma_ok": self.sigma_ok,
            "harmonie_ok": self.harmonie_ok,
            "safe_haven_ok": self.safe_haven_ok,
            "sigma_value": round(self.sigma_value, 2),
            "harmonie_details": self.harmonie_details,
            "safe_haven_details": self.safe_haven_details,
            "downgrade_reason": self.downgrade_reason,
        }


def fatboy_gate(
    fatman_scores_m30: Dict[str, float],
    fatman_scores_h1: Dict[str, float],
    pair: str,
    *,
    sigma_convergence: float = SIGMA_CONVERGENCE,
    sigma_divergence: float = SIGMA_DIVERGENCE,
    safe_haven_top_n: int = 3,
) -> FatboyGateResult:
    """
    Gate Fatboy (Option C Hybrid) — applique les 3 principes Fatboy comme meta-filter.

    Doctrine V10 Option C :
      - Ne bloque PAS le signal (R6 fail-open)
      - Retourne downgrade_reason pour downgrade progressif dans orchestrateur :
        A1→A2, A2→A3, A3→NONE si l'un des 3 principes échoue
      - Utilisé dans compose_signal_with_context() comme couche additionnelle

    Args:
        fatman_scores_m30: scores 8 devises sur M30 (ex: {'USD': 50, 'EUR': 40, ...})
        fatman_scores_h1:  scores 8 devises sur H1
        pair: paire concernée (ex: 'AUDUSD')

    Returns:
        FatboyGateResult avec passed=True si les 3 principes OK
    """
    # Principe 1 — Sigma convergence/divergence
    sigma = _safe_sigma(0, 0, list(fatman_scores_m30.values()))
    sigma_ok, sigma_reason = principle_sigma_check(sigma)

    # Principe 2 — Harmonies TF (M30 aligné avec H1)
    harmonie_ok = principle_harmonie_tf(fatman_scores_m30, fatman_scores_h1, pair)
    harmonie_details = "aligned" if harmonie_ok else "M30≠H1"

    # Principe 3 — Safe Haven filter
    safe_haven_ok = principle_safe_haven_filter(fatman_scores_m30, top_n=safe_haven_top_n)
    if safe_haven_ok:
        safe_haven_details = "ok"
    else:
        # Identifier quelles devises safe haven sont dans le top
        sorted_scores = sorted(fatman_scores_m30.items(), key=lambda kv: kv[1], reverse=True)
        top_currencies = {c for c, _ in sorted_scores[:safe_haven_top_n]}
        sh_in_top = top_currencies & SAFE_HAVEN_CURRENCIES
        safe_haven_details = f"safe_haven_in_top_{safe_haven_top_n}: {sh_in_top}"

    # Résultat global
    passed = sigma_ok and harmonie_ok and safe_haven_ok
    downgrade_reason = ""
    if not sigma_ok:
        downgrade_reason = "sigma_zone_grise"
    elif not harmonie_ok:
        downgrade_reason = "harmonie_m30_h1"
    elif not safe_haven_ok:
        downgrade_reason = "safe_haven_active"

    return FatboyGateResult(
        passed=passed,
        sigma_ok=sigma_ok,
        harmonie_ok=harmonie_ok,
        safe_haven_ok=safe_haven_ok,
        sigma_value=sigma,
        harmonie_details=harmonie_details,
        safe_haven_details=safe_haven_details,
        downgrade_reason=downgrade_reason,
    )


# ─────────────────────────────────────────────────────────────────────
# Composite — applique TOUS les filtres sur un signal candidat
# ─────────────────────────────────────────────────────────────────────
@dataclass
class BibleSignalWithFilters:
    """Signal + résultats des 6 filtres appliqués."""
    signal: BibleSignalResult
    filters_passed: Dict[str, bool] = field(default_factory=dict)
    filters_reasons: Dict[str, str] = field(default_factory=dict)
    is_actionable: bool = False

    def as_dict(self) -> Dict:
        return {
            "signal": self.signal.as_dict(),
            "filters_passed": dict(self.filters_passed),
            "filters_reasons": dict(self.filters_reasons),
            "is_actionable": self.is_actionable,
        }


def apply_all_filters(
    signal: BibleSignalResult,
    *,
    hour_utc: int,
    atr_now: float,
    avg_atr_20d: float,
    spread_now: float,
    spread_avg_daily: float,
    sigma: float,
    candidate_pair: str,
    corr_with_open: Optional[Dict[str, float]] = None,
    open_pairs: Optional[List[str]] = None,
    minutes_to_news: Optional[int] = None,
) -> BibleSignalWithFilters:
    """Applique les 6 filtres Bible Edge Fund au signal."""
    fs = signal.filters_passed if hasattr(signal, "filters_passed") else {}
    rs = signal.filters_reasons if hasattr(signal, "filters_reasons") else {}
    out = BibleSignalWithFilters(signal=signal)

    def _record(r: BibleFilterResult) -> None:
        out.filters_passed[r.filter_id] = r.passed
        out.filters_reasons[r.filter_id] = r.reason

    _record(filter_session(hour_utc))
    _record(filter_atr_dynamics(atr_now, avg_atr_20d))
    _record(filter_spread(spread_now, spread_avg_daily))
    _record(filter_correlation_with_open_positions(
        candidate_pair, corr_with_open or {}, open_pairs or [],
    ))
    _record(filter_news_window(minutes_to_news))
    _record(filter_sigma(sigma))
    out.is_actionable = all(out.filters_passed.values())
    return out


# ─────────────────────────────────────────────────────────────────────
# __all__
# ─────────────────────────────────────────────────────────────────────
__all__ = [
    # Constantes (ré-exportées)
    "GAP_STANDARD",
    "GAP_INSTITUTION",
    "SIGMA_CONVERGENCE",
    "SIGMA_DIVERGENCE",
    "SAFE_HAVEN_CURRENCIES",
    # Dataclasses
    "BibleSignalResult",
    "BibleFilterResult",
    "BibleSignalWithFilters",
    "FatboyGateResult",
    # 6 signaux
    "signal_1_forte_faible",
    "signal_2_inst",
    "signal_3_divergence",
    "signal_4_safe_haven_flip",
    "signal_5_convergence",
    "signal_6_continuation_mtf",
    # 6 filtres
    "filter_session",
    "filter_atr_dynamics",
    "filter_spread",
    "filter_correlation_with_open_positions",
    "filter_news_window",
    "filter_sigma",
    # 4 principes
    "principle_sigma_check",
    "principle_harmonie_tf",
    "principle_safe_haven_filter",
    "principle_volume_required",
    # Fatboy Gate (Option C Hybrid)
    "fatboy_gate",
    # Composite
    "apply_all_filters",
]
