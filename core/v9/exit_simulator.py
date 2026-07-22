"""ExitSimulator — Stratégies de sortie professionnelles (Phase 13.2).

Simule des stratégies de sortie réalistes pour le paper-trading :
  - TP_SL       : Take-profit et stop-loss fixes
  - TRAILING    : Trailing stop (accroche les gains)
  - TIME_BASED  : Sortie à horizon fixe (H1, H4, etc.)
  - MFE_ONLY    : MFE pur (backward compat, référence académique)
  - DYNAMIC     : TP/SL adaptatif par session de marché (Asie/London/NY/After)

La stratégie DYNAMIC est la recommandation CEO Phase 13.2 :
  - Asie       : TP=10, SL=15 (WR 95.4%, +7.6 pips/trade)
  - London     : TP=8,  SL=15 (WR 81.3%, +3.2 pips/trade)
  - Overlap    : TP=5,  SL=15 (WR 86.1%, +1.9 pips/trade)
  - New York   : TP=10, SL=15 (WR 29.6%, -7.5 — risque élevé, scaling réduit)
  - After      : TP=10, SL=15 (WR 20.6%, -10.6 — risque élevé, scaling réduit)

Usage :
    simulator = ExitSimulator(strategy="DYNAMIC")
    result = simulator.simulate(entry=1.3368, direction="baissiere",
                                future_mids=[...], session_marche="asie")
    # → TP=10/SL=15 adapté à la session Asie
"""
from __future__ import annotations

import enum
from typing import Any


class ExitStrategy(str, enum.Enum):
    """Stratégies de sortie supportées."""
    TP_SL = "TP_SL"               # Take-profit + Stop-loss fixes
    TRAILING = "TRAILING"         # Trailing stop
    TIME_BASED = "TIME_BASED"     # Sortie à horizon fixe
    MFE_ONLY = "MFE_ONLY"         # MFE pur (référence, backward compat)
    DYNAMIC = "DYNAMIC"           # TP/SL adaptatif par session (RECOMMANDÉE)


# ── Résultat de simulation ─────────────────────────────────────────

class ExitResult:
    """Résultat structuré d'une simulation de sortie.

    Attributs :
        pips (float)        : Pips réalisés (positif = gain, négatif = perte)
        is_win (int)        : 1 si gain > 0, 0 sinon
        exit_reason (str)   : Raison de sortie (tp_hit, sl_hit, trailing_stop, time_exit, mfe_end)
        exit_price (float)  : Prix de sortie simulé
        entry_price (float) : Prix d'entrée
        max_favorable (float): Plus haut/bas atteint (valeur absolue en pips)
        max_adverse (float) : Plus bas/haut adverse (valeur absolue en pips)
        bars_held (int)     : Nombre de barres avant sortie
    """
    __slots__ = (
        "pips", "is_win", "exit_reason", "exit_price",
        "entry_price", "max_favorable", "max_adverse", "bars_held",
    )

    def __init__(
        self,
        pips: float,
        is_win: int,
        exit_reason: str,
        exit_price: float,
        entry_price: float,
        max_favorable: float,
        max_adverse: float,
        bars_held: int,
    ) -> None:
        self.pips = pips
        self.is_win = is_win
        self.exit_reason = exit_reason
        self.exit_price = exit_price
        self.entry_price = entry_price
        self.max_favorable = max_favorable
        self.max_adverse = max_adverse
        self.bars_held = bars_held

    def to_dict(self) -> dict[str, Any]:
        return {
            "pips": self.pips,
            "is_win": self.is_win,
            "exit_reason": self.exit_reason,
            "exit_price": self.exit_price,
            "entry_price": self.entry_price,
            "max_favorable": self.max_favorable,
            "max_adverse": self.max_adverse,
            "bars_held": self.bars_held,
        }

    def __repr__(self) -> str:
        return (
            f"ExitResult(pips={self.pips:+.1f}, win={self.is_win}, "
            f"reason={self.exit_reason}, held={self.bars_held})"
        )


# ── Convertisseur prix ↔ pips ─────────────────────────────────────

PIPS_MULTIPLIER = 10000  # GBPUSD/EURUSD 4 décimales (défaut historique, inchangé)

# Brief Q4 (multi-paires, 2026-07-13) : les paires cotées en JPY (2 décimales)
# ont un multiplicateur pips différent (100, pas 10000). Toute paire absente
# de cette table — dont GBPUSD, qui n'y figure jamais — retombe sur
# PIPS_MULTIPLIER=10000, comportement historique strictement préservé.
JPY_QUOTE_PIPS_MULTIPLIER = 100
JPY_QUOTED_SYMBOLS = {"USDJPY", "GBPJPY"}


def pips_multiplier_for_symbol(symbol: str | None) -> int:
    """Multiplicateur prix->pips pour un symbole donné.

    GBPUSD, EURUSD, symbole absent/None -> 10000 (défaut historique).
    Paires cotées en JPY (USDJPY, GBPJPY) -> 100."""
    if symbol in JPY_QUOTED_SYMBOLS:
        return JPY_QUOTE_PIPS_MULTIPLIER
    return PIPS_MULTIPLIER


def price_to_pips(price_diff: float, multiplier: int = PIPS_MULTIPLIER) -> float:
    """Convertit une différence de prix en pips.

    `multiplier` par défaut = 10000 (GBPUSD/EURUSD, comportement historique
    inchangé pour tout appelant existant qui ne passe pas cet argument).
    Passer `pips_multiplier_for_symbol(symbol)` pour une paire JPY."""
    return round(price_diff * multiplier, 1)


# ── Profils DYNAMIC par session ────────────────────────────────────

# Matrice de décision issue de l'analyse des 9512 décisions (Phase 13.2)
# Chaque profil donne : TP, SL, et un facteur de scaling (1.0 = normal)
DYNAMIC_PROFILES: dict[str, dict[str, float]] = {
    # 2026-07-22 — Recalibrage RR équilibré (motion CEO « fait tout »).
    # Ancien : TP=5-10, SL=15 → RR=0.33-0.67, breakeven WR=60-75% (irréaliste).
    # Nouveau : TP=10, SL=10 partout → RR=1.0, breakeven WR=50%.
    # Le système a WR 45% → avec RR=1.0, EV=-0.5 pip (vs -1.0 avant).
    # L'objectif est que le Bayesian (T+30j) amène WR>50% → rentabilité.
    "asie":       {"tp_pips": 10.0, "sl_pips": 10.0, "scale": 1.0},
    "london":     {"tp_pips": 10.0, "sl_pips": 10.0, "scale": 0.8},
    "overlap":    {"tp_pips": 10.0, "sl_pips": 10.0, "scale": 0.6},
    "new_york":   {"tp_pips": 10.0, "sl_pips": 10.0, "scale": 0.3},
    "after":      {"tp_pips": 10.0, "sl_pips": 10.0, "scale": 0.2},
}

# Profil par défaut si session inconnue
DYNAMIC_DEFAULT = {"tp_pips": 10.0, "sl_pips": 10.0, "scale": 1.0}


# ── Brief O4 — Décision CEO 2026-07-13 ────────────────────────────────────
# Sessions structurellement perdantes (Phase 13.2 calibration empirique 9512 décisions) :
#   - New York : WR 29.6%, -7.5 pips/trade
#   - After    : WR 20.6%, -10.6 pips/trade
# Décision formelle CEO 2026-07-13 (DECISIONS_LOG §O4) : politique
# conservatrice, exclusion structurelle de la tradabilité DYNAMIC.
# Le profil DYNAMIC est conservé (descriptif, R25') mais
# `is_session_tradable()` retourne False → `_recommend_dynamic_*` retourne
# None et `decision_logger`/`risk_manager` doivent refuser en defense-in-depth.
# 2026-07-15 : overlap ajouté à la blacklist (expectancy -2.26 pips/trade
# confirmée par replay benchmark sur 215 décisions — TP 5 trop serré vs SL 15,
# ratio R/R 0.33 exige WR > 75% pour break-even, observé 63.7%).
# 2026-07-17 17:05 — Motion CEO « go débloquer tout fait tout pour go » :
#   Réactivation overlap + after avec sizing réduit (scale 0.3 / 0.2) plutôt
#   qu'exclusion pure. Le CEO senior quant considère que le blocage total est
#   auto-disqualifiant : on trade pour apprendre, on protège via sizing.
#   Seul new_york reste en exclusion structurelle (WR 29.6% inacceptable).
#   Le profil DYNAMIC de chaque session reste consultable (descriptif) ; la
#   tradabilité est désormais fonction du sizing via DynamicRiskManager APPLY
#   (commit c6afebb, motion CEO 2026-07-17).
# 2026-07-17 18:08 — Motion CEO « continue optimiser au max » :
#   new_york réactivée aussi. Sizing scale 0.2 dans DYNAMIC_PROFILES (le
#   profile conservait déjà 0.3 → réduit à 0.2). Le CEO considère que le
#   marché new_york IS le marché le plus liquide — bloquer = perdre alpha.
#   Blacklist sessions désormais VIDE. Le contrôle se fait par sizing adaptatif
#   dans DYNAMIC_PROFILES + DynamicRiskManager APPLY (cycle/phase/coalition).
# 2026-07-17 22:00 — Audit senior quant ZCode :
#   WR réel = 23%, -10 pips/trade. La blacklist vide est trop permissive.
#   new_york (WR 0%) et after (WR 0%) sont structurellement perdants.
#   overlap (WR 63.7%) est marginal — gardé avec sizing réduit.
#   Restauration blacklist conservatrice : new_york + after exclus.
DYNAMIC_BLACKLIST_SESSIONS = frozenset({"new_york", "after"})

# Sessions « tradables » = total - blacklist (helper cache).
# Inversé pour lisibilité côté consommateur
DYNAMIC_TRADABLE_SESSIONS = frozenset(
    set(DYNAMIC_PROFILES.keys()) - DYNAMIC_BLACKLIST_SESSIONS
)


def is_session_tradable(session_marche: str) -> bool:
    """Décision O4 CEO 2026-07-13 : retourne False pour new_york et after.

    Politique conservatrice : sessions à WR structurellement faible et pips
    moyens négatifs (Phase 13.2 calibration). Helper pur sans dépendance DB,
    testable directement. Réversible — changer la constante suffit à
    ré-activer une session (cf DECISIONS_LOG pour le détail doctrinal).
    """
    return session_marche in DYNAMIC_TRADABLE_SESSIONS


def infer_session_from_hour(utc_hour: int) -> str:
    """Infère la session de marché depuis l'heure UTC.

    Heuristique conservative :
      - asie     : 00:00-07:00 UTC
      - london   : 07:00-12:00 UTC
      - overlap  : 12:00-16:00 UTC (London+NY)
      - new_york : 16:00-22:00 UTC
      - after    : 22:00-00:00 UTC
    """
    if 0 <= utc_hour < 7:
        return "asie"
    if 7 <= utc_hour < 12:
        return "london"
    if 12 <= utc_hour < 16:
        return "overlap"
    if 16 <= utc_hour < 22:
        return "new_york"
    return "after"


# ── Simulateur principal ───────────────────────────────────────────

class ExitSimulator:
    """Simulateur de stratégies de sortie.

    Paramètres :
        strategy (str)      : Stratégie parmi ExitStrategy
        tp_pips (float)     : Take-profit en pips (défaut 20.0, utilisé par TP_SL et fallback DYNAMIC)
        sl_pips (float)     : Stop-loss en pips (défaut 10.0)
        trailing_dist (float): Distance du trailing stop en pips (défaut 15.0)
        time_bars (int)     : Nombre de barres max pour TIME_BASED (défaut 4)
        spread_pips (float) : Spread estimé en pips (défaut 0.5)
        symbol (str | None) : Symbole (Brief Q4, multi-paires) — détermine le
                               multiplicateur pips (JPY vs 4 décimales).
                               défaut None -> 10000, comportement historique
                               strictement inchangé pour tout appelant existant.
    """
    def __init__(
        self,
        strategy: str = "TP_SL",
        *,
        tp_pips: float = 20.0,
        sl_pips: float = 10.0,
        trailing_dist: float = 15.0,
        time_bars: int = 4,
        spread_pips: float = 0.5,
        symbol: str | None = None,
    ) -> None:
        if strategy not in [e.value for e in ExitStrategy]:
            valid = ", ".join(e.value for e in ExitStrategy)
            raise ValueError(f"Stratégie inconnue : {strategy}. Valides : {valid}")
        self.strategy = strategy
        self.tp_pips = tp_pips
        self.sl_pips = sl_pips
        self.trailing_dist = trailing_dist
        self.time_bars = time_bars
        self.spread_pips = spread_pips
        self.symbol = symbol
        self._pips_multiplier = pips_multiplier_for_symbol(symbol)

    def _price_to_pips(self, price_diff: float) -> float:
        """Convertit une différence de prix en pips avec le multiplicateur de
        CETTE instance (dépend de `symbol` — 10000 par défaut/GBPUSD/EURUSD,
        100 pour les paires JPY)."""
        return price_to_pips(price_diff, self._pips_multiplier)

    def simulate(
        self,
        entry: float,
        direction: str,
        future_mids: list[float],
        session_marche: str | None = None,
        utc_hour: int | None = None,
    ) -> ExitResult:
        """Simule la sortie selon la stratégie configurée.

        Args:
            entry: Prix d'entrée (mid)
            direction: "haussiere" ou "baissiere"
            future_mids: Liste des prix futurs (triés par timestamp ASC)
            session_marche: Session de marché (asie/london/overlap/new_york/after)
                            Optionnel, utilisé uniquement par DYNAMIC.
                            Si None, inféré depuis utc_hour.
            utc_hour: Heure UTC pour inférer la session si session_marche non fournie.

        Returns:
            ExitResult structuré
        """
        if not future_mids:
            return ExitResult(
                pips=0.0, is_win=0, exit_reason="no_data",
                exit_price=entry, entry_price=entry,
                max_favorable=0.0, max_adverse=0.0, bars_held=0,
            )

        if self.strategy == ExitStrategy.MFE_ONLY:
            return self._simulate_mfe(entry, direction, future_mids)
        elif self.strategy == ExitStrategy.DYNAMIC:
            return self._simulate_dynamic(entry, direction, future_mids,
                                          session_marche, utc_hour)
        elif self.strategy == ExitStrategy.TP_SL:
            return self._simulate_tp_sl(entry, direction, future_mids,
                                        self.tp_pips, self.sl_pips)
        elif self.strategy == ExitStrategy.TRAILING:
            # P4 : auto-optimizer peut activer cassure_aware via strategy_overrides.
            # Lecture best-effort, défaut False (comportement historique préservé).
            cassure_aware = bool(
                getattr(self, "_cassiure_aware_flag", False)
            )
            return self._simulate_trailing(
                entry, direction, future_mids, cassure_aware=cassure_aware
            )
        elif self.strategy == ExitStrategy.TIME_BASED:
            return self._simulate_time_based(entry, direction, future_mids)
        else:
            return self._simulate_mfe(entry, direction, future_mids)

    # ── DYNAMIC — TP/SL adaptatif par session ─────────────────────

    def _simulate_dynamic(
        self,
        entry: float,
        direction: str,
        mids: list[float],
        session_marche: str | None = None,
        utc_hour: int | None = None,
    ) -> ExitResult:
        """Simulation avec TP/SL adapté à la session de marché.

        La session est déterminée par :
          1. session_marche (explicite, prioritaire)
          2. utc_hour (inféré)
          3. "asie" (défaut conservateur)
        """
        if session_marche is None and utc_hour is not None:
            session_marche = infer_session_from_hour(utc_hour)
        elif session_marche is None:
            session_marche = "asie"  # défaut conservateur

        profile = DYNAMIC_PROFILES.get(session_marche, DYNAMIC_DEFAULT)
        tp_pips = profile["tp_pips"]
        sl_pips = profile["sl_pips"]

        # La simulation TP/SL utilise les pips du profil
        result = self._simulate_tp_sl(entry, direction, mids, tp_pips, sl_pips)

        # Ajouter la session dans l'exit_reason pour traçabilité
        result.exit_reason = f"{result.exit_reason}_{session_marche}"

        return result

    # ── MFE (Maximum Favorable Excursion) — référence académique ──

    def _simulate_mfe(
        self, entry: float, direction: str, mids: list[float],
    ) -> ExitResult:
        """MFE pur : prend le meilleur prix atteint."""
        if direction == "haussiere":
            best = max(mids)
            worst = min(mids)
            pips_raw = best - entry
        else:
            best = min(mids)
            worst = max(mids)
            pips_raw = entry - best

        pips = self._price_to_pips(pips_raw) - self.spread_pips
        mfe = self._price_to_pips(abs(best - entry))
        mae = self._price_to_pips(abs(worst - entry))

        return ExitResult(
            pips=pips,
            is_win=1 if pips > 0 else 0,
            exit_reason="mfe_end",
            exit_price=best,
            entry_price=entry,
            max_favorable=mfe,
            max_adverse=mae,
            bars_held=len(mids),
        )

    # ── TP/SL fixes ──────────────────────────────────────────────

    def _simulate_tp_sl(
        self, entry: float, direction: str, mids: list[float],
        tp_pips: float | None = None,
        sl_pips: float | None = None,
    ) -> ExitResult:
        """TP et SL fixes. Sortie au premier atteint.

        Règles de marché :
          - Haussière : TP = entry + tp_pips_px, SL = entry - sl_pips_px
          - Baissière : TP = entry - tp_pips_px, SL = entry + sl_pips_px
          - Le spread est soustrait du gain (ajouté à la perte)
        """
        tp = tp_pips if tp_pips is not None else self.tp_pips
        sl = sl_pips if sl_pips is not None else self.sl_pips
        tp_px = tp / self._pips_multiplier
        sl_px = sl / self._pips_multiplier
        spread_px = self.spread_pips / self._pips_multiplier

        if direction == "haussiere":
            tp_level = entry + tp_px
            sl_level = entry - sl_px
            for i, price in enumerate(mids):
                if price >= tp_level:
                    gain = tp - self.spread_pips
                    return ExitResult(
                        pips=gain, is_win=1, exit_reason="tp_hit",
                        exit_price=price, entry_price=entry,
                        max_favorable=tp,
                        max_adverse=self._price_to_pips(max(0, entry - min(mids[:i+1]))),
                        bars_held=i + 1,
                    )
                if price <= sl_level:
                    loss = -(sl + self.spread_pips)
                    return ExitResult(
                        pips=loss, is_win=0, exit_reason="sl_hit",
                        exit_price=price, entry_price=entry,
                        max_favorable=self._price_to_pips(max(0, max(mids[:i+1]) - entry)),
                        max_adverse=sl,
                        bars_held=i + 1,
                    )
        else:  # baissiere
            tp_level = entry - tp_px
            sl_level = entry + sl_px
            for i, price in enumerate(mids):
                if price <= tp_level:
                    gain = tp - self.spread_pips
                    return ExitResult(
                        pips=gain, is_win=1, exit_reason="tp_hit",
                        exit_price=price, entry_price=entry,
                        max_favorable=tp,
                        max_adverse=self._price_to_pips(max(0, max(mids[:i+1]) - entry)),
                        bars_held=i + 1,
                    )
                if price >= sl_level:
                    loss = -(sl + self.spread_pips)
                    return ExitResult(
                        pips=loss, is_win=0, exit_reason="sl_hit",
                        exit_price=price, entry_price=entry,
                        max_favorable=self._price_to_pips(max(0, entry - min(mids[:i+1]))),
                        max_adverse=sl,
                        bars_held=i + 1,
                    )

        # Ni TP ni SL touché → sortie au dernier prix
        last = mids[-1]
        if direction == "haussiere":
            pips_raw = last - entry
        else:
            pips_raw = entry - last
        pips = self._price_to_pips(pips_raw) - self.spread_pips
        mfe = self._price_to_pips(abs((max(mids) if direction == "haussiere" else min(mids)) - entry))
        mae = self._price_to_pips(abs((min(mids) if direction == "haussiere" else max(mids)) - entry))

        return ExitResult(
            pips=pips, is_win=1 if pips > 0 else 0,
            exit_reason="time_end",
            exit_price=last, entry_price=entry,
            max_favorable=mfe, max_adverse=mae,
            bars_held=len(mids),
        )

    # ── Trailing Stop ───────────────────────────────────────────

    def _simulate_trailing(
        self, entry: float, direction: str, mids: list[float],
        cassure_aware: bool = False,
    ) -> ExitResult:
        """Trailing stop : le stop suit le prix en sa faveur.

        Principe :
          - Haussière : trailing_stop = max(seen) - trailing_dist_px
          - Baissière : trailing_stop = min(seen) + trailing_dist_px
          - Sortie quand le prix repasse le trailing stop

        Mode cassure_aware (P4 2026-07-16) :
          Le trailing n'est activé qu'une fois le prix dans la moitié du TP
          (MFE ≥ MIN_MFE_RATIO × TP, défaut 0.5). Avant ce seuil, on suit le
          prix pour accumuler le MFE sans serrer la sortie. Distance trailing
          = sl × DIST_SL_RATIO (au lieu de trailing_dist fixe).
        """
        from core.v9 import config as _v9_cf  # lazy import (évite cycle config->exit)
        min_mfe_ratio = _v9_cf.TRAILING_CASSURE_MIN_MFE_RATIO
        dist_sl_ratio = _v9_cf.TRAILING_CASSURE_DIST_SL_RATIO
        tp_pips = self.tp_pips
        sl_pips = self.sl_pips

        def _distance_pips(mfe_pips_now: float) -> float:
            """Distance trailing effective, dépend du mode."""
            if not cassure_aware:
                return self.trailing_dist
            # Si on n'a pas atteint le seuil MFE → trailing « infini » (désactivé).
            if mfe_pips_now < min_mfe_ratio * tp_pips:
                return 1e9
            # Sinon trailing serré = sl * ratio.
            return sl_pips * dist_sl_ratio

        if direction == "haussiere":
            best = entry
            for i, price in enumerate(mids):
                if price > best:
                    best = price
                mfe_pips = self._price_to_pips(best - entry)
                trail_pips = _distance_pips(mfe_pips)
                trail_px = trail_pips / self._pips_multiplier
                if trail_pips >= 1e9:
                    continue  # trailing désactivé tant que MFE < seuil
                trail_level = best - trail_px
                if price <= trail_level:
                    pips_raw = price - entry
                    pips = self._price_to_pips(pips_raw) - self.spread_pips
                    return ExitResult(
                        pips=pips, is_win=1 if pips > 0 else 0,
                        exit_reason="trailing_stop",
                        exit_price=price, entry_price=entry,
                        max_favorable=mfe_pips,
                        max_adverse=self._price_to_pips(entry - min(mids[:i+1])),
                        bars_held=i + 1,
                    )
        else:  # baissiere
            best = entry
            for i, price in enumerate(mids):
                if price < best:
                    best = price
                mfe_pips = self._price_to_pips(entry - best)
                trail_pips = _distance_pips(mfe_pips)
                trail_px = trail_pips / self._pips_multiplier
                if trail_pips >= 1e9:
                    continue  # trailing désactivé tant que MFE < seuil
                trail_level = best + trail_px
                if price >= trail_level:
                    pips_raw = entry - price
                    pips = self._price_to_pips(pips_raw) - self.spread_pips
                    return ExitResult(
                        pips=pips, is_win=1 if pips > 0 else 0,
                        exit_reason="trailing_stop",
                        exit_price=price, entry_price=entry,
                        max_favorable=mfe_pips,
                        max_adverse=self._price_to_pips(max(mids[:i+1]) - entry),
                        bars_held=i + 1,
                    )

        # Jamais sorti par le trailing → sortie au dernier prix
        last = mids[-1]
        if direction == "haussiere":
            pips_raw = last - entry
        else:
            pips_raw = entry - last
        pips = self._price_to_pips(pips_raw) - self.spread_pips
        mfe = self._price_to_pips(abs((max(mids) if direction == "haussiere" else min(mids)) - entry))
        mae = self._price_to_pips(abs((min(mids) if direction == "haussiere" else max(mids)) - entry))

        return ExitResult(
            pips=pips, is_win=1 if pips > 0 else 0,
            exit_reason="time_end",
            exit_price=last, entry_price=entry,
            max_favorable=mfe, max_adverse=mae,
            bars_held=len(mids),
        )

    # ── Time-based ──────────────────────────────────────────────

    def _simulate_time_based(
        self, entry: float, direction: str, mids: list[float],
    ) -> ExitResult:
        """Sortie après N barres (indépendant du prix)."""
        n = min(self.time_bars, len(mids))
        price = mids[n - 1]

        if direction == "haussiere":
            pips_raw = price - entry
        else:
            pips_raw = entry - price
        pips = self._price_to_pips(pips_raw) - self.spread_pips
        mfe = self._price_to_pips(abs((max(mids[:n]) if direction == "haussiere" else min(mids[:n])) - entry))
        mae = self._price_to_pips(abs((min(mids[:n]) if direction == "haussiere" else max(mids[:n])) - entry))

        return ExitResult(
            pips=pips, is_win=1 if pips > 0 else 0,
            exit_reason="time_exit",
            exit_price=price, entry_price=entry,
            max_favorable=mfe, max_adverse=mae,
            bars_held=n,
        )
