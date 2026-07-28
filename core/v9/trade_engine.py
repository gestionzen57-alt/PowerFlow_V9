"""TradeEngine — Point d'entrée unique pour la simulation de trade V9.

Consolide en un seul module :
  - Arbiter (consolidation vote multi-signaux)
  - RiskManager + PaperRiskManager (gate go/no-go + sizing + drawdown)
  - ExitSimulator (SL/TP réels par session, pas hardcodés)
  - PaperTradeLogger (ouverture/clôture en DB)
  - PyramidingEngine (scaling sur confluence)

Avant : 4 modules dispersés + 7 scripts, chaîne non câblée au pipeline live.
Maintenant : un seul module, appelable depuis l'orchestrator (hook post-décision)
ou depuis le superviseur (--paper-trade).

Architecture :
  orchestrator.run_chain()
    └── decision_logger → action="preparer_entree"
         └── trade_engine.process(snapshot_id)   ← HOOK
              ├── arbiter.consolidate()
              ├── paper_risk_manager.evaluate()
              ├── exit_simulator (pour clôture avec pips réels)
              └── paper_trade_logger.log_open() / log_close()

Doctrine :
  - R18 : aucun LLM dans la boucle (code pur)
  - R2 : couche additive (n'affecte pas la chaîne cognitive existante)
  - R6 : try/except sur chaque étape, ne crash jamais l'orchestrator
  - R25' : propose-only pour le pyramiding (descriptif, pas d'auto-promotion)
  - Phase 12 : exécution réelle INTERDITE, simulation uniquement
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.arbiter import Arbiter
from core.v9.config import (
    CVAR_BUDGET_PIPS,
    CVAR_CONFIDENCE,
    CVAR_LOOKBACK_TRADES,
    CVAR_MIN_TRADES,
    DB_PATH,
)
from core.v9.db_schema import get_connection
from core.v9.exit_simulator import (
    DYNAMIC_PROFILES,
    ExitSimulator,
    ExitStrategy,
    infer_session_from_hour,
    is_session_tradable,
    pips_multiplier_for_symbol,
    price_to_pips,
)
from core.v9 import kill_switches  # noqa: E402  (2026-07-20 P0 fix : kill_switches.get() centralise env>fichier>defaut)
from core.v9.kill_switches import (
    paper_trade_halt_enabled as _paper_trade_halt_enabled,
    drawdown_protector_enabled as _drawdown_protector_enabled,
    risk_parity_enabled as _risk_parity_enabled,
)
from core.v9.paper_risk_manager import PaperRiskManager
from core.v9.paper_trade_logger import PaperTradeLogger
from core.v9.pyramiding_engine import PyramidingEngine
from core.v9.v9_dynamic_tp_sl import compute_dynamic_tp_sl, dynamic_tp_sl_enabled
from core.v9.v9_loop_breaker import check_loop, loop_breaker_enabled

# MetaStrategy Optimizer (Phase E, J14) — câblage optionnel, import défensif (R6).
# Le hook (section 3a7) reste inerte tant que META_STRATEGY_AVAILABLE est
# False (import cassé) OU que le kill switch V9_META_STRATEGY_OPTIMIZER_ENABLED est OFF.
try:
    from core.v9.v9_meta_strategy_optimizer import (
        select_strategy as _meta_select_strategy,
        MetaStrategyDecision,
        meta_strategy_optimizer_enabled as _meta_strategy_optimizer_enabled,
    )
    META_STRATEGY_AVAILABLE = True
except ImportError:
    META_STRATEGY_AVAILABLE = False

# Kelly Fractionnel (Axe 1.2 J2) — câblage optionnel, import défensif (R6).
# Le hook de sizing (section 3a4) reste inerte tant que KELLY_AVAILABLE est
# False (import cassé) OU que le kill switch V9_KELLY_FRACTIONAL_ENABLED est OFF.
try:
    from core.v9.v9_kelly_sizing import (
        KellySizingEngine,
        apply_kelly_to_sizing,
        build_context_key,
    )
    from core.v9.kill_switches import kelly_fractional_enabled as _kelly_fractional_enabled
    KELLY_AVAILABLE = True
except ImportError:
    KELLY_AVAILABLE = False

# UnifiedSizingEngine (Phase E.1, 2026-07-28) — composition multiplicative
# finale (base × portfolio_risk × dd_protector × risk_parity × kelly × meta_strategy).
# Bornes [0.1, 3.0] dures. Kill switch V9_UNIFIED_SIZING_ENABLED (défaut ON,
# motion Hermès 2026-07-27). R2 additif, R6 jamais bloquant (fallback composition
# ad-hoc si module absent ou kill switch OFF).
try:
    from core.v9.unified_sizing import (
        compute_unified_sizing,
        get_unified_sizing_engine,
    )
    from core.v9.kill_switches import unified_sizing_enabled as _unified_sizing_enabled
    UNIFIED_SIZING_AVAILABLE = True
except ImportError:
    UNIFIED_SIZING_AVAILABLE = False

# Drawdown Protector (Axe 3.2 J11) — câblage optionnel, import défensif (R6).
# Le hook (section 3a5) reste inerte tant que DD_PROTECTOR_AVAILABLE est
# False (import cassé) OU que le kill switch V9_DRAWDOWN_PROTECTOR_ENABLED est OFF.
try:
    from core.v9.v9_drawdown_protector import DrawdownProtector
    from core.v9.kill_switches import drawdown_protector_enabled
    DD_PROTECTOR_AVAILABLE = True
except ImportError:
    DD_PROTECTOR_AVAILABLE = False

# Risk Parity (Axe 3.3 J12) — câblage optionnel, import défensif (R6).
# Le hook (section 3a6) reste inerte tant que RISK_PARITY_AVAILABLE est
# False (import cassé) OU que le kill switch V9_RISK_PARITY_ENABLED est OFF.
try:
    from core.v9.v9_risk_parity import (
        compute_risk_parity_budgets,
        PairRiskBudget,
        HARD_BLACKLIST,
    )
    RISK_PARITY_AVAILABLE = True
except ImportError:
    RISK_PARITY_AVAILABLE = False
    HARD_BLACKLIST = {"USDCAD"}  # fallback

log = logging.getLogger(__name__)

TRADE_ENGINE_VERSION = "1.0"

# Kill switch : si OFF, le trade_engine ne fait rien (hook inerte).
TRADE_ENGINE_ENV = "V9_TRADE_ENGINE_ENABLED"

# Kill switch du DynamicRiskManager (Phase 13.3). Défaut ON en mode SHADOW :
# le module ÉVALUE la gestion de risque adaptative et attache le résultat au
# diagnostic (`result["dynamic_risk"]`), mais n'APPLIQUE rien — le SL/TP
# réellement utilisé reste celui calculé par la chaîne existante. Passer à "0"
# désactive complètement l'évaluation shadow. L'activation (mode APPLY) est une
# décision CEO, non câblée ici.
DYNAMIC_RISK_ENV = "V9_DYNAMIC_RISK_ENABLED"

# Kill switch long-only transitoire GBPUSD (Tâche 4, mission baissier 2/2).
# Défaut OFF. Si "1" : pour GBPUSD UNIQUEMENT, toute décision baissière est
# forcée en 'haussiere' (drift structurel +46 pips/j identifié, le baissier
# GBPUSD perd à 1.2% WR sur 3709 trades). Additif (R2) : `long_only_override`.
GBPUSD_LONG_ONLY_ENV = "V9_GBPUSD_LONG_ONLY"
NO_BAISSIERE_ENV = "V9_NO_BAISSIERE"

# Kill switch du PortfolioRiskManager (niveau quantique P0, câblé 2026-07-18).
# Défaut ON : le PRM évalue le risque au niveau portfolio (exposition nette par
# devise, corrélation entre paires, portfolio heat, circuit breaker N pertes
# consécutives, drawdown 24h) AVANT l'ouverture. Il peut BLOQUER le trade
# (result["action"]="skip") ou RÉDUIRE le sizing (corrélation élevée). Additif
# (R2) : n'altère jamais la chaîne cognitive, seulement le gate d'ouverture.
# Passer à "0" le rend inerte.
PORTFOLIO_RISK_ENV = "V9_PORTFOLIO_RISK_ENABLED"


def _trade_engine_enabled() -> bool:
    """Kill switch du trade_engine. Défaut ON (Phase 12 simulation).

    2026-07-20 P0 fix : lit via core.v9.kill_switches.get() au lieu de
    os.environ.get() direct. Le wrapper v9_load_kill_switches.py charge
    le .env dans os.environ au boot cron, mais cet ordre n'est PAS
    garanti (cas subprocess directs). kill_switches.get() lit le .env
    en fallback → switch effectif même sans wrapper.
    """
    return kill_switches.get(TRADE_ENGINE_ENV, "1") not in ("0", "", "false", "False")


def _portfolio_risk_enabled() -> bool:
    """Kill switch du PortfolioRiskManager. Défaut ON.

    Cf. _trade_engine_enabled() — utilise kill_switches.get() pour
    respecter la hiérarchie env > fichier > défaut.
    """
    return kill_switches.get(PORTFOLIO_RISK_ENV, "1") not in ("0", "", "false", "False")


# Kill switch du MarketRegimeGlobal (niveau quantique P3, risk-on/off).
# Défaut OFF (R2 : le DRM APPLY reste inchangé tant que non activé). Si "1",
# le régime global (force USD + sentiment risk-on/off) est calculé et injecté
# dans le DynamicRiskManager comme modulateur de TP. Activation = décision CEO.
MARKET_REGIME_GLOBAL_ENV = "V9_MARKET_REGIME_GLOBAL_ENABLED"


def _market_regime_global_enabled() -> bool:
    """Kill switch du MarketRegimeGlobal. Défaut OFF. Cf. _trade_engine_enabled()."""
    return kill_switches.get(MARKET_REGIME_GLOBAL_ENV, "0") in ("1", "true", "True")


# Kill switch du plafond CVaR (Chantier B, 2026-07-18). Défaut OFF : le sizing
# Kelly existant (paper_risk_manager) reste inchangé. Si "1", position_size est
# plafonné par le budget CVaR 95%. Le sizing Kelly live a un verdict NO-GO
# walk-forward (DECISIONS_LOG) — activation = override CEO explicite.
KELLY_CVAR_ENV = "V9_KELLY_CVAR_ENABLED"


def _kelly_cvar_enabled() -> bool:
    """Kill switch du plafond CVaR. Défaut OFF. Cf. _trade_engine_enabled()."""
    return kill_switches.get(KELLY_CVAR_ENV, "0") in ("1", "true", "True")


def _gbpusd_long_only_enabled() -> bool:
    """Kill switch long-only GBPUSD (Tâche 4). Défaut OFF (transitoire).

    2026-07-20 P0 fix : utilise kill_switches.get() au lieu de os.environ.get()
    direct. Sinon le switch est OFF en runtime car le cron V9_PaperTradeLoop
    ne charge pas systématiquement le .env avant d'invoquer le supervisor
    (cf. incident 14h15 UTC : trade GBPUSD short passé alors que
    V9_GBPUSD_LONG_ONLY=1 dans le fichier).
    """
    return kill_switches.get(GBPUSD_LONG_ONLY_ENV, "0") in ("1", "true", "True")


def _no_baissiere_enabled() -> bool:
    """Kill switch no-baisiere GLOBAL (motion CEO 2026-07-18 §15h35).

    Si ON : force `direction='haussiere'` pour TOUTES les paires
    (pas seulement GBPUSD). Justification : edge baissier catastrophique
    = -56 178 pips sur 3709 trades baissiers (WR 1.21 %), edge haussier
    sain = +8 850 pips sur 1108 trades (WR 98.83 %). Bilan global
    = -47 327 pips.

    Additif (R2) : `no_baissiere_override` dans le résultat.

    2026-07-20 P0 fix : idem _gbpusd_long_only_enabled() — utilise
    kill_switches.get() au lieu de os.environ.get() direct pour garantir
    l'application effective en runtime cron.
    """
    return kill_switches.get(NO_BAISSIERE_ENV, "0") in ("1", "true", "True")


def _dynamic_risk_enabled() -> bool:
    """Kill switch du DynamicRiskManager (SHADOW). Défaut ON.

    Cf. _trade_engine_enabled() — utilise kill_switches.get().
    """
    return kill_switches.get(DYNAMIC_RISK_ENV, "1") not in ("0", "", "false", "False")

def _execution_simulation_enabled() -> bool:
    """Mode simulation (ordres isolés /sim/). Défaut ON."""
    return os.environ.get("V9_EXECUTION_SIMULATION", "1") in ("1", "true", "True")


class TradeEngine:
    """Moteur de simulation de trade unifié V9.

    Un seul point d'entrée pour :
      1. Consolider les signaux (Arbiter)
      2. Évaluer le risque (PaperRiskManager : go/no-go + sizing + drawdown)
      3. Évaluer le pyramiding (PyramidingEngine : descriptif)
      4. Ouvrir un paper-trade (PaperTradeLogger)
      5. Clôturer avec SL/TP réels (ExitSimulator, pas hardcodés)

    Usage depuis l'orchestrator :
        engine = TradeEngine()
        result = engine.process(snapshot_id)

    Usage depuis le superviseur :
        engine = TradeEngine()
        result = engine.run_batch(limit=20)
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        self._arbiter: Arbiter | None = None
        self._risk_mgr: PaperRiskManager | None = None
        self._logger: PaperTradeLogger | None = None
        self._pyramiding: PyramidingEngine | None = None
        self._cascade: Any = None
        self._active_cascades: list[dict[str, Any]] | None = None
        self._dynamic_risk: Any = None
        self._portfolio_risk: Any = None
        self._market_regime_global: Any = None
        self._batch_global_regime: Any = None
        # Kelly Fractionnel (Axe 1.2 J2) — lazy, câblé section 3a4 (défaut OFF).
        self._kelly_engine: Any = None
        self._last_snapshot_id: str | None = None

    # ── Lazy singletons (évite recharger à chaque call) ──

    @property
    def arbiter(self) -> Arbiter:
        if self._arbiter is None:
            self._arbiter = Arbiter(db_path=self.db_path)
        return self._arbiter

    @property
    def risk_manager(self) -> PaperRiskManager:
        if self._risk_mgr is None:
            self._risk_mgr = PaperRiskManager()
        return self._risk_mgr

    @property
    def trade_logger(self) -> PaperTradeLogger:
        if self._logger is None:
            self._logger = PaperTradeLogger(db_path=self.db_path)
        return self._logger

    @property
    def pyramiding_engine(self) -> PyramidingEngine:
        if self._pyramiding is None:
            self._pyramiding = PyramidingEngine()
        return self._pyramiding

    @property
    def cascade_engine(self) -> Any:
        """PrincipleCascadeEngine (lazy — SOUL.md §5, booster de confiance)."""
        if self._cascade is None:
            from core.v9.principle_cascade_engine import PrincipleCascadeEngine
            self._cascade = PrincipleCascadeEngine(db_path=self.db_path)
        return self._cascade

    @property
    def dynamic_risk_manager(self) -> Any:
        """DynamicRiskManager (lazy — Phase 13.3, SL/TP adaptatifs SHADOW)."""
        if self._dynamic_risk is None:
            from core.v9.dynamic_risk_manager import DynamicRiskManager
            self._dynamic_risk = DynamicRiskManager()
        return self._dynamic_risk

    @property
    def portfolio_risk_manager(self) -> Any:
        """PortfolioRiskManager (lazy — niveau quantique P0, risque portfolio)."""
        if self._portfolio_risk is None:
            from core.v9.portfolio_risk_manager import PortfolioRiskManager
            self._portfolio_risk = PortfolioRiskManager(db_path=self.db_path)
        return self._portfolio_risk

    @property
    def market_regime_global(self) -> Any:
        """MarketRegimeGlobal (lazy — niveau quantique P3, risk-on/off)."""
        if self._market_regime_global is None:
            from core.v9.market_regime_global import MarketRegimeGlobal
            self._market_regime_global = MarketRegimeGlobal(db_path=self.db_path)
        return self._market_regime_global

    @property
    def kelly_engine(self) -> Any:
        """KellySizingEngine (lazy — Axe 1.2 J2, multiplicateur Kelly bayésien).

        Construit un BayesianCalibrator (lecture seule DB) + KellySizingEngine.
        R6 : None si l'import ou la construction échoue (hook inerte)."""
        if self._kelly_engine is None and KELLY_AVAILABLE:
            try:
                from core.v9.bayesian_calibrator import BayesianCalibrator
                calibrator = BayesianCalibrator(self.db_path)
                self._kelly_engine = KellySizingEngine(calibrator, self.db_path)
            except Exception as exc:
                log.warning("trade_engine: KellySizingEngine init failed: %s", exc)
        return self._kelly_engine

    @property
    def kelly_sizing_report(self) -> dict | None:
        """Snapshot lecture seule du multiplicateur Kelly pour le dernier
        snapshot traité (observabilité). None si le câblage est indisponible,
        le kill switch OFF (défaut), ou aucun snapshot traité. Aucun effet de
        bord — n'altère pas le sizing (celui-ci est appliqué dans process())."""
        if not KELLY_AVAILABLE or not self._last_snapshot_id:
            return None
        engine = self.kelly_engine
        if engine is None or not engine.is_enabled():
            return None
        ctx = self._current_context_key(self._last_snapshot_id)
        if ctx is None:
            return None
        return engine.compute_multiplier(ctx)

    def _current_context_key(self, snapshot_id: str) -> tuple | None:
        """Clé de contexte Kelly (principle, symbol, tf, session, regime) du
        snapshot. Délègue à `v9_kelly_sizing.build_context_key` (lecture ro).
        R6 : None si indisponible."""
        if not KELLY_AVAILABLE:
            return None
        try:
            return build_context_key(self.db_path, snapshot_id)
        except Exception as exc:
            log.debug("trade_engine: context_key build failed [%s]: %s", snapshot_id, exc)
            return None

    def _get_global_regime(self) -> Any:
        """Régime global (cache par instance/batch). None si kill switch OFF.

        Le régime global évolue lentement (minutes) : on le calcule une fois
        par batch plutôt qu'à chaque snapshot. R6 : None si échec/désactivé.
        """
        if not _market_regime_global_enabled():
            return None
        if self._batch_global_regime is None:
            try:
                self._batch_global_regime = self.market_regime_global.detect()
            except Exception as exc:
                log.debug("trade_engine: global regime detect failed: %s", exc)
                self._batch_global_regime = None
        return self._batch_global_regime

    def _get_active_cascades(self) -> list[dict[str, Any]]:
        """Cascades boosters actives (chargées une fois par instance)."""
        if self._active_cascades is None:
            try:
                self._active_cascades = self.cascade_engine.get_active_cascades()
            except Exception:
                self._active_cascades = []
        return self._active_cascades

    # ── API principale ──

    def process(self, snapshot_id: str) -> dict[str, Any]:
        """Traite un snapshot : arbiter → risk → open (si go).

        Retourne un dict structuré avec le résultat complet.
        Ne lève jamais d'exception (R6 — try/except par étape).
        """
        result: dict[str, Any] = {
            "snapshot_id": snapshot_id,
            "trade_id": None,
            "action": "skip",
            "direction": None,
            "confiance": 0,
            "risk_go": False,
            "raison_blocage": None,
            "tp_pips": None,
            "sl_pips": None,
            "strategy": None,
            "session": None,
            "pyramiding": None,
            "error": None,
        }
        # Kelly Fractionnel (Axe 1.2 J2) : mémorise le dernier snapshot traité
        # pour la propriété d'observabilité `kelly_sizing_report`. Aucun effet
        # sur le flux (prepare → enter → manage → exit reste intact).
        self._last_snapshot_id = snapshot_id

        # 0. P0 2026-07-19 : kill switch V9_PAPER_TRADE_HALT.
        # R6 fail-safe : HALT TOTAL du paper-trading (recommandé par le
        # watchdog critique, remplace l'ancienne reco V9_GBPUSD_LONG_ONLY=0
        # qui ré-autorisait les shorts). Vérifié EN PREMIER (avant l'arbiter)
        # pour éviter de payer le coût cognitif + DB d'une consolidation si
        # le halt est demandé. Pas de paper-trade ouvert, pas de log
        # trade_logger.log_open, pas de motion NO_ENTREE remontée par
        # RiskManager — on retourne juste skip + raison=paper_halt.
        if _paper_trade_halt_enabled():
            result["raison_blocage"] = "paper_halt"
            return result

        # 1. Arbiter — consolidation
        try:
            arbiter_result = self.arbiter.consolidate(snapshot_id)
        except Exception as exc:
            result["error"] = f"arbiter: {exc}"
            log.debug("trade_engine: arbiter failed [%s]: %s", snapshot_id, exc)
            return result

        result["direction"] = arbiter_result.get("direction")
        result["confiance"] = arbiter_result.get("confiance_arbitree", 0)

        # 1b. Long-only transitoire GBPUSD (Tâche 4, mission baissier 2/2).
        # Kill switch V9_GBPUSD_LONG_ONLY (défaut OFF). Si ON : pour GBPUSD
        # UNIQUEMENT, une décision baissière est forcée en 'haussiere' (le
        # baissier GBPUSD perd à 1.2% WR sur 3709 trades, drift structurel
        # +46 pips/j). Les autres paires ne sont JAMAIS touchées. Additif
        # (R2) : `long_only_override`. R6 : résolution symbole défensive.
        result["long_only_override"] = False
        if _gbpusd_long_only_enabled():
            try:
                symbol_lo, _ = self._resolve_symbol_and_decision(snapshot_id)
                if (
                    symbol_lo == "GBPUSD"
                    and str(result["direction"] or "").lower() == "baissiere"
                ):
                    arbiter_result["direction"] = "haussiere"
                    result["direction"] = "haussiere"
                    result["long_only_override"] = True
            except Exception as exc:  # R6 — jamais bloquant.
                log.debug(
                    "trade_engine: long_only override failed [%s]: %s",
                    snapshot_id, exc,
                )

        # 1c. No-baissière GLOBAL (motion CEO 2026-07-18 §15h35).
        # Kill switch V9_NO_BAISSIERE (défaut OFF). Si ON : TOUTES les
        # décisions baissières (toutes paires) sont forcées en 'haussiere'.
        # Justification : edge baissier catastrophique = -56 178 pips sur
        # 3709 trades baissiers (WR 1.21 %), edge haussier sain = +8 850
        # pips sur 1108 trades (WR 98.83 %). Bilan global = -47 327 pips.
        # Additif (R2) : `no_baissiere_override`. R6 : résolution symbole
        # défensive. Note : si V9_GBPUSD_LONG_ONLY=1 ET V9_NO_BAISSIERE=1,
        # les deux overrides s'appliquent (le GBPUSD long-only est un cas
        # particulier du no-baissière global). Idempotent.
        result["no_baissiere_override"] = False
        if _no_baissiere_enabled():
            try:
                _, _ = self._resolve_symbol_and_decision(snapshot_id)
                if str(result["direction"] or "").lower() == "baissiere":
                    arbiter_result["direction"] = "haussiere"
                    result["direction"] = "haussiere"
                    result["no_baissiere_override"] = True
            except Exception as exc:  # R6 — jamais bloquant.
                log.debug(
                    "trade_engine: no_baissiere override failed [%s]: %s",
                    snapshot_id, exc,
                )

        # 1d. Loop Breaker générique (motion CEO 2026-07-18 §17h15).
        # Kill switch V9_LOOP_BREAKER_ENABLED (défaut OFF). Si ON : interroge
        # check_loop(symbol, direction) AVANT d'ouvrir le trade. Si la décision
        # n'est pas allowed, le trade est skippé (action="skip" + raison).
        # Justification : catastrophe 17/07 = 4750 trades GBPUSD baissier,
        # 962 dans la minute 16:05, 88% fermés en 0 min. Boucle re-entry sans
        # cooldown ni limite positions. Anti-pattern : signal persistant +
        # exécution sans garde-fou. R2 additif : si OFF ou erreur DB → skip
        # ce bloc, flux normal. R6 : try/except jamais bloquant.
        if loop_breaker_enabled():
            try:
                lb_symbol, _ = self._resolve_symbol_and_decision(snapshot_id)
                lb_dir = str(result["direction"] or "").lower()
                if lb_symbol and lb_dir:
                    loop_decision = check_loop(
                        symbol=str(lb_symbol),
                        direction=lb_dir,
                        db_path=self.db_path,
                    )
                    result["loop_breaker"] = {
                        "allowed": loop_decision.allowed,
                        "reason": loop_decision.reason,
                        "n_recent_trades": loop_decision.n_recent_trades,
                        "action": loop_decision.action,
                    }
                    if not loop_decision.allowed:
                        result["action"] = "skip"
                        result["raison_blocage"] = (
                            f"loop_breaker: {loop_decision.reason}"
                        )
                        log.info(
                            "[LOOP_BREAKER] trade skipped [%s]: %s",
                            snapshot_id, loop_decision.reason,
                        )
                        return result
            except Exception as exc:  # R6 — jamais bloquant.
                log.debug(
                    "trade_engine: loop_breaker check failed [%s]: %s",
                    snapshot_id, exc,
                )

        # 2. Session check (blacklist Brief O4)
        # 2026-07-17 motion CEO: utilise session précalculée par run_batch
        # (même pour tous dans un batch court). Fallback calcul direct sinon.
        # Recalcule si >5 min depuis la dernière mise à jour (sécurité batch long).
        hour_utc = datetime.now(timezone.utc).hour
        session = infer_session_from_hour(hour_utc)
        cached_sess = getattr(self, "_batch_session", None)
        cached_sess_time = getattr(self, "_batch_session_time", None)
        now = datetime.now(timezone.utc)
        if cached_sess is None or cached_sess_time is None or (
            now - cached_sess_time
        ).total_seconds() > 300:
            self._batch_session = session
            self._batch_session_time = now
        else:
            session = cached_sess
        result["session"] = session

        if not is_session_tradable(session):
            result["action"] = "skip"
            result["raison_blocage"] = f"session_blacklisted ({session})"
            return result

        # 2b. Cascade confidence boost (SOUL.md §3 — booster de confiance)
        # Si une cascade booster valide matche les principes de ce snapshot,
        # la confiance est amplifiée AVANT le gate risk_manager. R6 : jamais
        # bloquant, R2 : additif (le boost ne fait qu'augmenter la confiance).
        result["cascade_boost"] = 0.0
        result["cascades_matched"] = []
        try:
            cascades = self.cascade_engine.get_cascade_for_snapshot(
                snapshot_id, self._get_active_cascades(),
            )
            if cascades:
                boosted = self.cascade_engine.apply_cascade_confidence_boost(
                    arbiter_result, cascades,
                )
                arbiter_result = boosted
                new_conf = boosted.get("confiance_arbitree_boosted")
                if new_conf is not None:
                    arbiter_result["confiance_arbitree"] = new_conf
                    result["confiance"] = new_conf
                result["cascade_boost"] = boosted.get("cascade_boost", 0.0)
                result["cascades_matched"] = boosted.get("cascades_matched", [])
        except Exception as exc:
            log.debug("trade_engine: cascade boost failed [%s]: %s", snapshot_id, exc)

        # 3. RiskManager — gate go/no-go + sizing + drawdown
        context = self._build_context(snapshot_id, session)
        # 2026-07-17 motion CEO: utilise open_trades préchargés par run_batch
        # (gain perf ~80% sur gros batchs : -1 requête par snapshot).
        cached = getattr(self, "_batch_open_trades", None)
        open_trades = cached if cached is not None else self._get_open_trades()

        try:
            risk_result = self.risk_manager.evaluate(
                arbiter_result, context, open_trades,
            )
        except Exception as exc:
            result["error"] = f"risk_manager: {exc}"
            log.debug("trade_engine: risk_manager failed [%s]: %s", snapshot_id, exc)
            return result

        result["risk_go"] = risk_result["go"]
        result["raison_blocage"] = risk_result.get("raison_blocage")

        if not risk_result["go"]:
            result["action"] = "skip"
            return result

        # 3a2. PortfolioRiskManager — risque au niveau portfolio (P0 quantique).
        # Câblé 2026-07-18 : après le gate risk_manager (trade isolé) et AVANT
        # l'ouverture. Un stratège institutionnel gère le risque au niveau
        # portfolio, pas par trade isolé. Le PRM vérifie : exposition nette par
        # devise, corrélation entre paires ouvertes, portfolio heat, circuit
        # breaker (N pertes consécutives), drawdown 24h. Il peut BLOQUER le
        # trade ou RÉDUIRE le sizing (corrélation élevée). Kill switch
        # V9_PORTFOLIO_RISK_ENABLED (défaut ON). R6 : jamais bloquant sur erreur.
        result["portfolio_risk"] = None
        result["correlation_sizing_reduction"] = None
        if _portfolio_risk_enabled():
            try:
                # symbole : context (si peuplé) sinon résolution DB/snapshot_id.
                symbol = context.get("symbol")
                if not symbol:
                    symbol, _ = self._resolve_symbol_and_decision(snapshot_id)
                new_trade_ctx = {
                    "symbol": symbol,
                    "direction": arbiter_result.get("direction"),
                    "risk_amount": risk_result.get("risk_amount", 100),
                    "capital": self.risk_manager.capital,
                }
                prm_go, prm_reason, sizing_mult = (
                    self.portfolio_risk_manager.evaluate_portfolio(
                        open_trades, new_trade_ctx,
                    )
                )
                result["portfolio_risk"] = {
                    "go": prm_go,
                    "reason": prm_reason,
                    "sizing_mult": sizing_mult,
                }
                if not prm_go:
                    result["action"] = "skip"
                    result["raison_blocage"] = prm_reason
                    return result
                # Réduction de sizing si corrélation élevée (pas un refus).
                if sizing_mult < 1.0 and "position_size" in risk_result:
                    risk_result["position_size"] = round(
                        risk_result["position_size"] * sizing_mult, 2
                    )
                    result["correlation_sizing_reduction"] = sizing_mult
            except Exception as exc:
                log.debug(
                    "trade_engine: PRM failed [%s]: %s", snapshot_id, exc,
                )

        # 3a3. CVaR ceiling — sizing institutionnel (Chantier B, 2026-07-18).
        # Le sizing Kelly est déjà appliqué en amont (paper_risk_manager) : on
        # NE le recalcule PAS (décision CEO « réutiliser, ne pas dupliquer »).
        # On plafonne seulement position_size par un budget CVaR 95% estimé sur
        # les returns récents de la paire (taille max = CVAR_BUDGET_PIPS / cvar).
        # Kill switch V9_KELLY_CVAR_ENABLED défaut OFF -> sizing inchangé.
        # R6 : jamais bloquant sur erreur.
        result["cvar_ceiling"] = None
        if _kelly_cvar_enabled() and "position_size" in risk_result:
            try:
                from core.v9.risk_manager import RiskManager

                cvar_symbol = context.get("symbol")
                if not cvar_symbol:
                    cvar_symbol, _ = self._resolve_symbol_and_decision(snapshot_id)
                returns = self._recent_returns_pips(cvar_symbol, CVAR_LOOKBACK_TRADES)
                if len(returns) >= CVAR_MIN_TRADES:
                    capped = RiskManager.cvar_position_cap(
                        risk_result["position_size"], returns,
                        CVAR_BUDGET_PIPS, CVAR_CONFIDENCE,
                    )
                    if capped["capped"]:
                        result["cvar_ceiling"] = {
                            "cvar": capped["cvar"],
                            "cap": capped["cap"],
                            "position_size_before": risk_result["position_size"],
                            "n_returns": len(returns),
                        }
                        risk_result["position_size"] = capped["size"]
            except Exception as exc:
                log.debug("trade_engine: CVaR ceiling failed [%s]: %s", snapshot_id, exc)

        # 3a4. Kelly Fractionnel — sizing bayésien-borné (Axe 1.2 J2, 2026-07-21).
        # Câblage NON-INTRUSIF derrière kill switch V9_KELLY_FRACTIONAL_ENABLED
        # (défaut OFF, R25' strict). Si ON : multiplie `position_size` par un
        # multiplicateur Kelly ∈ [0.3, 2.0] dérivé du posterior Beta(α,β) réel
        # du contexte (principle × symbol × tf × session × regime). Composition
        # MULTIPLICATIVE avec le sizing existant (Kelly × ce que paper_risk /
        # PRM / CVaR ont déjà décidé) — jamais un remplacement. Neutre (×1.0) si
        # n<20, edge non confirmé (P(WR>0.5)<0.6), ou erreur. Justification :
        # Brier 7j = 0.4467 (confiance déclarée anti-calibrée) → le sizing sur
        # confiance déclarée est anti-Kelly. R2 additif, R6 jamais bloquant.
        result["kelly_sizing"] = None
        if (
            KELLY_AVAILABLE
            and _kelly_fractional_enabled()
            and "position_size" in risk_result
        ):
            try:
                ctx_key = self._current_context_key(snapshot_id)
                if ctx_key is not None and self.kelly_engine is not None:
                    kelly_applied = apply_kelly_to_sizing(
                        base_size=risk_result["position_size"],
                        kelly_engine=self.kelly_engine,
                        context_key=ctx_key,
                        dynamic_risk_multiplier=1.0,
                    )
                    result["kelly_sizing"] = kelly_applied
                    if kelly_applied["applied"]:
                        risk_result["position_size"] = round(
                            kelly_applied["final_size"], 2
                        )
                        post = (kelly_applied.get("report") or {}).get("posterior") or {}
                        log.info(
                            "[KELLY] mult=%.3f size %.2f→%.2f (n=%s mean=%.3f) ctx=%s",
                            kelly_applied["kelly_multiplier"],
                            kelly_applied["base_size"],
                            risk_result["position_size"],
                            post.get("n"), post.get("mean", 0.0), ctx_key,
                        )
            except Exception as exc:  # R6 — jamais bloquant.
                log.debug("trade_engine: kelly sizing failed [%s]: %s", snapshot_id, exc)
            # 3a5. Drawdown Protector — sizing multiplicatif adaptatif (Axe 3.2 J11, 2026-07-21).
            # Câblage NON-INTRUSIF derrière kill switch V9_DRAWDOWN_PROTECTOR_ENABLED
            # (défaut OFF, R25' strict). Si ON : multiplie `position_size` par un
            # multiplicateur position_multiplier ∈ [0.0, 1.0] dérivé de l'état DD
            # (5 paliers : normal 1.0, reduce_50 0.5, halt_24h 0.0, halt_forever 0.0,
            # recovery progressif 0.25→0.5→0.75→1.0). Composition MULTIPLICATIVE
            # avec le sizing existant — jamais un remplacement. Neutre (×1.0) si
            # import cassé, kill switch OFF, ou erreur. R2 additif, R6 jamais bloquant.
            result["drawdown_protector"] = None
            if (
                DD_PROTECTOR_AVAILABLE
                and _drawdown_protector_enabled()
                and "position_size" in risk_result
            ):
                            try:
                                dd_protector = DrawdownProtector(
                                    initial_capital=self.risk_manager.capital,
                                    db_path=self.db_path,
                                )
                                dd_decision = dd_protector.decide()
                                result["drawdown_protector"] = dd_decision.to_dict()
                                if dd_decision.position_multiplier < 1.0 and "position_size" in risk_result:
                                    risk_result["position_size"] = round(
                                        risk_result["position_size"] * dd_decision.position_multiplier, 2
                                    )
                                    log.info(
                                        "[DD_PROTECTOR] action=%s mult=%.2f size %.2f→%.2f DD=%.1f%% rationale=%s",
                                        dd_decision.action,
                                        dd_decision.position_multiplier,
                                        risk_result["position_size"] / max(dd_decision.position_multiplier, 0.001),
                                        risk_result["position_size"],
                                        dd_decision.state_snapshot.get("current_drawdown", 0) / self.risk_manager.capital * 100,
                                        dd_decision.rationale,
                                    )
                            except Exception as exc:  # R6 — jamais bloquant.
                                log.debug("trade_engine: drawdown protector failed [%s]: %s", snapshot_id, exc)

            # 3a6. Risk Parity — budget de risque par paire (Axe 3.3 J12, 2026-07-21).
            # Câblage NON-INTRUSIF derrière kill switch V9_RISK_PARITY_ENABLED
            # (défaut ON per CEO motion). Si ON : applique le budget risk-parity
# (weight ∝ 1/vol × max(0.5, sharpe)) comme plafonnement multiplicatif
# du sizing par paire. USDCAD hard-blacklisté (WR 15.8% confirmé).
# Composition MULTIPLICATIVE avec sizing existant. Neutre si import cassé
# ou erreur. R2 additif, R6 jamais bloquant.
            if (

                RISK_PARITY_AVAILABLE

                and _risk_parity_enabled()

                and "position_size" in risk_result

            ):

                try:

                    symbol = context.get("symbol")

                    if not symbol:

                        symbol, _ = self._resolve_symbol_and_decision(snapshot_id)

                    if symbol not in HARD_BLACKLIST:

                        # Lazy init RiskParityEngine

                        if not hasattr(self, "_risk_parity_engine") or self._risk_parity_engine is None:

                            self._risk_parity_engine = RiskParityEngine(db_path=self.db_path)

                        budgets = self._risk_parity_engine.compute_budgets(

                            capital=self.risk_manager.capital,

                        )

                        # Trouver le budget pour ce symbole

                        for budget in budgets:

                            if budget.symbol == symbol:

                                result["risk_parity"] = budget.to_dict()

                                # Appliquer le plafonnement : position_size <= max_position_size

                                if budget.max_position_size > 0 and risk_result["position_size"] > budget.max_position_size:

                                    old_size = risk_result["position_size"]

                                    risk_result["position_size"] = round(budget.max_position_size, 2)

                                    log.info(

                                        "[RISK_PARITY] %s max_size=%.0f size %.2f->%.2f (weight=%.1f%% vol=%.0f sharpe=%.2f)",

                                        symbol,

                                        budget.max_position_size,

                                        old_size,

                                        risk_result["position_size"],

                                        budget.risk_weight * 100,

                                        budget.vol_annualized,

                                        budget.expected_sharpe,

                                    )

                                break

                except Exception as exc:  # R6 -- jamais bloquant.
                                    log.debug("trade_engine: risk parity failed [%s]: %s", snapshot_id, exc)


            # 3a7. Unified Sizing Engine (Phase E.1, 2026-07-28) — composition
            # multiplicative finale (base × portfolio_risk × dd_protector ×
            # risk_parity × kelly × meta_strategy). Bornes [0.1, 3.0] dures.
            # Kill switch V9_UNIFIED_SIZING_ENABLED (défaut ON, motion Hermès
            # 2026-07-27). R2 additif, R6 jamais bloquant (fallback composition
            # ad-hoc si module absent ou kill switch OFF). L'engine compose
            # tous les multiplicateurs amont en un seul final_multiplier, ce qui
            # simplifie l'audit et garantit la cohérence cross-paire.
            result["unified_sizing"] = None
            if (
                UNIFIED_SIZING_AVAILABLE
                and _unified_sizing_enabled()
                and "position_size" in risk_result
                and risk_result["position_size"] > 0
            ):
                try:
                    # Récupérer les multiplicateurs amont (déjà appliqués)
                    # par lecture des hooks précédents.
                    pr_mult = float(result.get("correlation_sizing_reduction") or 1.0)
                    dd_mult = float(result.get("dd_protector_multiplier") or 1.0)
                    rp_weight = float(result.get("risk_parity_weight") or 1.0)
                    kelly_applied_dict = result.get("kelly_sizing") or {}
                    kelly_mult = float(kelly_applied_dict.get("multiplier", 1.0)) if kelly_applied_dict.get("applied") else None
                    meta_strategy = arbiter_result.get("strategy") if isinstance(arbiter_result, dict) else None

                    sizing = compute_unified_sizing(
                        base_size=risk_result["position_size"],
                        context={
                            "principle_id": arbiter_result.get("principle_id") if isinstance(arbiter_result, dict) else None,
                            "symbol": snapshot.symbol if hasattr(snapshot, "symbol") else None,
                            "session": arbiter_result.get("session_marche") if isinstance(arbiter_result, dict) else None,
                            "regime": arbiter_result.get("regime_type") if isinstance(arbiter_result, dict) else None,
                        },
                        portfolio_risk_mult=pr_mult,
                        dd_protector_mult=dd_mult,
                        risk_parity_weight=rp_weight,
                        kelly_mult=kelly_mult,
                        meta_strategy=meta_strategy,
                    )
                    result["unified_sizing"] = sizing.to_dict()
                    if sizing.blocked:
                        log.info(
                            "trade_engine: unified_sizing BLOCKED [%s] reason=%s",
                            snapshot_id, sizing.block_reason,
                        )
                        # Si bloqué par portfolio_risk ou dd_protector, on bloque
                        # le trade (gate dur déjà respecté, ceinture+bretelles).
                        result["action"] = "skip"
                        result["skip_reason"] = f"unified_sizing_{sizing.block_reason}"
                    elif sizing.final_multiplier != 1.0:
                        # Composition multiplicative finale
                        risk_result["position_size"] = round(sizing.final_size, 2)
                        log.debug(
                            "trade_engine: unified_sizing applied [%s] mult=%.3f final_size=%.2f",
                            snapshot_id, sizing.final_multiplier, sizing.final_size,
                        )
                except Exception as exc:  # R6 -- jamais bloquant.
                    log.debug("trade_engine: unified_sizing failed [%s]: %s", snapshot_id, exc)



            # 3b. BearPerception -- evaluation SHADOW (Tache 1, mission baissier 2/2).


                        # 3b. BearPerception — évaluation SHADOW (Tâche 1, mission baissier 2/2).
        # Phase A du déploiement progressif R25' : le moteur CALCULE ce qu'il
        # ferait (skip baissier structurel, exit adaptatif rapide) et l'attache
        # au résultat sous des clés `bear_perception_would_*` (préfixe "would"
        # = hypothétique). AUCUNE action réelle : le flux, le TP/SL et la
        # direction restent inchangés. L'activation en mode APPLY (Phase B) est
        # une décision CEO séparée. Kill switch V9_BEAR_PERCEPTION_ENABLED
        # (défaut OFF) : si OFF, on n'évalue même pas. R6 : jamais bloquant.
        self._attach_bear_perception_shadow(result, snapshot_id, arbiter_result, context)

        # 4. SL/TP depuis le strategy_profile du principe (SOUL.md)
        # Priorité : strategy_profile du principe > signal > DYNAMIC fallback
        # 2026-07-17 motion CEO « continue optimiser au max » :
        # intègre StrategySelector (pôle stratégie) pour recommandation
        # data-driven basée sur l'historique paper_trades.
        signal_rec = self._fetch_signal_recommendation(snapshot_id)
        principes = arbiter_result.get("principes_source", [])
        primary_principle = principes[0] if principes else None

        strategy_profile = None
        regime = context.get("regime_type")
        if primary_principle:
            # 1. Catalogue du pôle stratégie (motion CEO 2026-07-17)
            try:
                if not hasattr(self, "_strategy_selector") or self._strategy_selector is None:
                    from core.v9.v9_strategy_pole import StrategySelector
                    self._strategy_selector = StrategySelector(db_path=self.db_path)
                rec = self._strategy_selector.recommend(
                    primary_principle, session, regime or "UNKNOWN",
                )
                if rec and rec.confidence > 0.5:
                    strategy_profile = {
                        "allowed": True,
                        "tp_pips": rec.recommended_tp,
                        "sl_pips": rec.recommended_sl,
                        "exit_strategy": rec.recommended_strategy,
                        "source": f"strategy_pole:{rec.source}",
                    }
            except Exception as exc:
                log.debug("trade_engine: strategy_pole selector failed: %s", exc)

            # 2. Fallback : PrincipleStrategyEngine (YAML + overrides)
            if not strategy_profile:
                try:
                    if not hasattr(self, "_pse_singleton") or self._pse_singleton is None:
                        from core.v9.principle_strategy_engine import PrincipleStrategyEngine
                        self._pse_singleton = PrincipleStrategyEngine()
                    pse = self._pse_singleton
                    strategy_profile = pse.get_strategy(primary_principle, session, regime)
                except Exception:
                    pass

        if strategy_profile and strategy_profile.get("allowed"):
            tp_pips = strategy_profile.get("tp_pips", 10.0)
            sl_pips = strategy_profile.get("sl_pips", 15.0)
            strategy = strategy_profile.get("exit_strategy", "TP_SL")
            result["strategy_source"] = strategy_profile.get("source", "profile")
        else:
            tp_pips = signal_rec.get("tp_pips_recommended") or 10.0
            sl_pips = signal_rec.get("sl_pips_recommended") or 15.0
            strategy = signal_rec.get("exit_strategy_recommended") or "DYNAMIC"
            result["strategy_source"] = "signal_fallback"

        # 3a7. MetaStrategy Optimizer (Phase E, J14) — sélection contextuelle
        # de stratégie (TP_SL / TRAILING / TP_PARTIAL / FAST_EXIT) basée sur
        # cycle_memory + principle_scores + paper_trades. Câblage NON-INTRUSIF
        # derrière kill switch V9_META_STRATEGY_OPTIMIZER_ENABLED (défaut ON
        # per CEO motion 2026-07-18). Remplace TP/SL/strategy si score > 0.
        # R2 additif, R6 jamais bloquant, R8 lecture seule DB.
        result["meta_strategy"] = None
        if (
            META_STRATEGY_AVAILABLE
            and _meta_strategy_optimizer_enabled()
            and primary_principle
            and regime
        ):
            try:
                symbol_ctx = context.get("symbol")
                if not symbol_ctx:
                    symbol_ctx, _ = self._resolve_symbol_and_decision(snapshot_id)
                timeframe_ctx = context.get("timeframe")
                if not timeframe_ctx:
                    timeframe_ctx = signal_rec.get("timeframe") or "M15"
                # Récupérer phase depuis behaviors + vol_atr_pips depuis regime_snapshots
                # On utilise le contexte complet chargé pour _get_full_context
                # Pour rester simple ici, on utilise des valeurs par défaut raisonnables
                # et le cycle_memory fait le rappel historique
                vol_atr_pips = context.get("vol_atr_pips")
                direction_ctx = arbiter_result.get("direction", "haussiere")
                
                # Essayer de charger phase et vol depuis DB
                phase_ctx = "initiation"
                try:
                    full_ctx = self._load_full_context(snapshot_id)
                    if full_ctx:
                        phase_ctx = full_ctx.get("behavior_phase", "initiation")
                        if vol_atr_pips is None:
                            vol_atr_pips = full_ctx.get("vol_atr_pips")
                except Exception:
                    pass
                
                meta_decision: MetaStrategyDecision = _meta_select_strategy(
                    symbol=symbol_ctx,
                    timeframe=timeframe_ctx,
                    regime_type=regime,
                    phase=phase_ctx,
                    vol_atr_pips=vol_atr_pips,
                    direction=direction_ctx,
                    db_path=self.db_path,
                    fallback_selector=self._strategy_selector if hasattr(self, "_strategy_selector") else None,
                )
                result["meta_strategy"] = meta_decision.to_dict()
                
                # Si le meta optimizer a un score > 0, on prend sa recommandation
                if meta_decision.confidence > 0 and meta_decision.chosen_strategy != "TP_SL":
                    tp_pips = meta_decision.recommended_tp
                    sl_pips = meta_decision.recommended_sl
                    strategy = meta_decision.chosen_strategy
                    result["strategy_source"] = "meta_strategy_optimizer"
                    log.info(
                        "[META_STRATEGY] %s %s chosen=%s TP=%.2f SL=%.2f conf=%.3f source=%s",
                        symbol_ctx, timeframe_ctx, meta_decision.chosen_strategy,
                        meta_decision.recommended_tp, meta_decision.recommended_sl,
                        meta_decision.confidence, meta_decision.source
                    )
            except Exception as exc:  # R6 — jamais bloquant.
                log.debug("trade_engine: meta_strategy optimizer failed [%s]: %s", snapshot_id, exc)

        result["tp_pips"] = tp_pips
        result["sl_pips"] = sl_pips
        result["strategy"] = strategy

        # 4a. Dynamic TP/SL (motion CEO 2026-07-18 §17h15).
        # Kill switch V9_DYNAMIC_TP_SL_ENABLED (défaut OFF). Si ON : override
        # les TP/SL hardcodés (RR=0.53) par magnitude historique réelle par
        # (symbol, timeframe). RR cible ≥ 0.7. R2 additif : si OFF ou erreur
        # DB → fallback hardcoded préservé. R6 : try/except jamais bloquant.
        if dynamic_tp_sl_enabled():
            try:
                dyn_symbol, _ = self._resolve_symbol_and_decision(snapshot_id)
                dyn_tf = (signal_rec.get("timeframe") or "M15") if signal_rec else "M15"
                if dyn_symbol:
                    dyn = compute_dynamic_tp_sl(
                        symbol=str(dyn_symbol),
                        timeframe=str(dyn_tf),
                        db_path=self.db_path,
                    )
                    tp_pips = float(dyn.tp)
                    sl_pips = float(dyn.sl)
                    result["tp_pips"] = tp_pips
                    result["sl_pips"] = sl_pips
                    result["dynamic_tp_sl"] = {
                        "tp": dyn.tp,
                        "sl": dyn.sl,
                        "rr_ratio": dyn.rr_ratio,
                        "source": dyn.source,
                        "rationale": dyn.rationale,
                    }
                    log.info(
                        "[DYN_TP_SL] %s %s TP=%.2f SL=%.2f RR=%.2f (%s)",
                        dyn_symbol, dyn_tf, dyn.tp, dyn.sl,
                        dyn.rr_ratio, dyn.source,
                    )
            except Exception as exc:  # R6 — jamais bloquant.
                log.debug(
                    "trade_engine: dynamic_tp_sl failed [%s]: %s",
                    snapshot_id, exc,
                )

        # 4b. DynamicRiskManager — APPLY (Phase 13.3, activé Søn 2026-07-17).
        # Évalue la gestion de risque adaptative (phase/cycle/coalition) et
        # APPLIQUE le SL/TP/exit sur le trade courant (motion CEO c6afebb).
        # Garde-fous : R6 (try/except silencieux, fallback statique) ; R2 (le
        # pipeline reste additif — `result["dynamic_risk"]` conserve le détail).
        # Si `phase == INDETERMINE` ou `source == "fallback"` : on conserve les
        # valeurs courantes. Si `allow_new_position == False` (climax) :
        # on force `action=skip` sans décision.
        result["dynamic_risk"] = None
        # P3 quantique : régime global risk-on/off (None si kill switch OFF).
        # Injecté dans le DRM comme modulateur de TP. R6 : _get_global_regime
        # ne lève jamais.
        global_regime = self._get_global_regime()
        result["market_regime_global"] = (
            global_regime.to_dict() if global_regime is not None else None
        )
        if _dynamic_risk_enabled():
            try:
                full_ctx = self._load_full_context(snapshot_id)
                risk_decision = self.dynamic_risk_manager.evaluate(
                    full_ctx,
                    decision={
                        "tp_pips": tp_pips,
                        "sl_pips": sl_pips,
                        "strategy": strategy,
                        "session_marche": session,
                    },
                    global_regime=global_regime,
                )
                result["dynamic_risk"] = risk_decision.to_dict()
                # APPLY: ne propage que les décisions calibrées dynamiquement.
                if (
                    risk_decision.source == "dynamic"
                    and risk_decision.allow_new_position
                ):
                    if risk_decision.tp_pips:
                        tp_pips = float(risk_decision.tp_pips)
                    if risk_decision.sl_pips:
                        sl_pips = float(risk_decision.sl_pips)
                    if risk_decision.exit_strategy:
                        strategy = risk_decision.exit_strategy
                    result["drm_applied"] = True
                elif risk_decision.source == "dynamic" and not risk_decision.allow_new_position:
                    # Phase climax (ou session non tradable) : pas de position.
                    result["action"] = "skip"
                    result["raison_blocage"] = (
                        f"drm_no_position (phase={risk_decision.phase}, "
                        f"session={risk_decision.session})"
                    )
                    result["drm_applied"] = True
                    return result
                # Conserve la cohérence result[].tp_pips/sl_pips/strategy
                # avec les locales éventuellement modifiées ci-dessus.
                result["tp_pips"] = tp_pips
                result["sl_pips"] = sl_pips
                result["strategy"] = strategy
            except Exception as exc:
                log.debug(
                    "trade_engine: dynamic_risk apply failed [%s]: %s",
                    snapshot_id, exc,
                )
                # R6 fallback silencieux sur les valeurs courantes.

        # 5. Pyramiding (descriptif — R25', pas d'auto-promotion)
        try:
            pyramiding_result = self.pyramiding_engine.evaluate(
                arbiter_result, context,
            )
            result["pyramiding"] = pyramiding_result
        except Exception:
            result["pyramiding"] = {"pyramiding_allowed": False, "multiplier": 1.0}

        # 6. Idempotence — pas de doublon (fix P0 2026-07-20)
        # Un snapshot = une décision = AU PLUS un paper_trade, ouvert OU fermé.
        # La garde historique ne comptait que les trades ENCORE ouverts : dès
        # qu'un trade était clôturé, le même snapshot_id redevenait éligible et
        # le hook (post_decision_hook, fresh TradeEngine par snapshot) le
        # ré-ouvrait au passage suivant → jusqu'à 7 paper_trades clôturés pour
        # un seul snapshot (catastrophe 17/07, récidive 19-20/07). Voir
        # `_trade_already_open` : compte désormais TOUT trade du couple
        # (snapshot_id, direction).
        if self._trade_already_open(snapshot_id, arbiter_result.get("direction")):
            result["action"] = "skip"
            result["raison_blocage"] = "snapshot_deja_trade"
            return result

        # 7. Ouvrir le paper-trade
        try:
            trade_id = self.trade_logger.log_open(
                arbiter_result, context,
            )
            result["trade_id"] = trade_id
            result["action"] = "open"
            # 2026-07-18 : coûts de transaction estimés pour audit
            try:
                from core.v9.transaction_costs import TransactionCosts
                costs = TransactionCosts()
                result["transaction_costs"] = costs.total_costs(
                    symbol=context.get("symbol"),
                    vol_regime=context.get("vol_regime"),
                )
                result["tp_pips_net"] = round(tp_pips - result["transaction_costs"], 2)
                result["sl_pips_net"] = round(sl_pips + result["transaction_costs"], 2)
                result["rr_net"] = round(
                    result["tp_pips_net"] / result["sl_pips_net"], 2
                ) if result["sl_pips_net"] > 0 else 0.0
            except Exception:
                pass
        except Exception as exc:
            result["error"] = f"log_open: {exc}"
            log.debug("trade_engine: log_open failed [%s]: %s", snapshot_id, exc)

        return result

    def run_batch(self, limit: int = 200) -> dict[str, Any]:  # 2026-07-17 motion CEO: élargi 20→200 pour exploiter les 8426 candidats live
        """Traite les N derniers snapshots avec décisions live.

        Ouvre les trades éligibles, puis clôture les trades ouverts
        avec SL/TP réels (ExitSimulator).

        2026-07-17 motion CEO « continue optimiser au max » :
        Optimisation performance — précharge la liste des open_trades UNE
        seule fois par batch (au lieu de N requêtes). Passe le contexte
        via _shared_batch_context pour économiser les requêtes par snapshot.

        Retourne un résumé : {opened, skipped, closed, wins, losses, wr}
        """
        snapshot_ids = self._fetch_recent_snapshots(limit)
        opened = 0
        skipped = 0
        errors = 0

        # 2026-07-17 motion CEO: précharge open_trades UNE fois par batch.
        # Gain mesuré : -80% du temps process() sur gros batchs.
        self._batch_open_trades = self._get_open_trades()

        # Précalcule session (même pour tous dans un batch court)
        from core.v9.exit_simulator import infer_session_from_hour
        batch_session = infer_session_from_hour(datetime.now(timezone.utc).hour)
        self._batch_session = batch_session

        for snapshot_id in snapshot_ids:
            try:
                result = self.process(snapshot_id)
                if result["action"] == "open":
                    opened += 1
                else:
                    skipped += 1
                if result.get("error"):
                    errors += 1
            except Exception:
                errors += 1

        # Clôture avec SL/TP réels
        close_result = self.close_open_trades()

        return {
            "opened": opened,
            "skipped": skipped,
            "errors": errors,
            "closed": close_result["closed"],
            "wins": close_result["wins"],
            "losses": close_result["losses"],
            "wr": close_result["wr"],
            "total_trades": close_result["total_trades"],
        }

    def close_open_trades(self) -> dict[str, Any]:
        """Clôture les paper_trades ouverts avec SL/TP réels via ExitSimulator.

        2026-07-17 audit CEO : avant, le code assignait pips_simulated = ±TP/SL
        conditionnellement à is_win (backtest artefactuel — pas de prix futurs
        lus). Maintenant : on lit les prix futurs réels depuis forces_snapshots
        (M5 après opened_at), on les passe à ExitSimulator qui simule
        path-dependent (TP/SL touché en premier, ou MFE/time-end).

        Si pas de prix futurs disponibles → fallback sur pips fixes (le mode
        historique backward-compat) AVEC un flag `is_artifact=1` pour audit.
        """
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        now_utc = datetime.now(timezone.utc).isoformat()

        # Compteur de trades clôturés AVANT ce batch (pour le seuil de
        # calibration tous les 100 trades — SOUL.md §4).
        closed_before = conn.execute(
            "SELECT COUNT(*) FROM paper_trades WHERE closed_at IS NOT NULL"
        ).fetchone()[0]

        # Trades ouverts avec leur décision et signal associés
        rows = conn.execute(
            """
            SELECT pt.trade_id, pt.snapshot_id, pt.direction, pt.opened_at,
                   d.is_win, d.decision_id, d.timestamp, d.symbol, d.timeframe,
                   d.regime_type, s.tp_pips_recommended, s.sl_pips_recommended,
                   s.exit_strategy_recommended
            FROM paper_trades pt
            JOIN decisions d ON d.snapshot_id = pt.snapshot_id
            LEFT JOIN signals s ON s.snapshot_id = pt.snapshot_id
            WHERE pt.closed_at IS NULL
              AND d.is_win IS NOT NULL
            ORDER BY pt.opened_at
            """
        ).fetchall()

        if not rows:
            total = conn.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
            conn.close()
            return {
                "closed": 0, "wins": 0, "losses": 0, "wr": 0.0,
                "total_trades": total, "calibration_triggered": False,
                "calibration": None,
            }

        # Import local pour éviter cycles
        from core.v9.exit_simulator import (
            ExitSimulator, ExitStrategy, infer_session_from_hour,
        )

        wins = 0
        losses = 0
        closed = 0
        artifact_count = 0  # count fallback sur pips fixes (pas de prix futurs)

        for r in rows:
            is_win_db = r["is_win"]
            tp_pips = r["tp_pips_recommended"] or 8.0
            sl_pips = r["sl_pips_recommended"] or 15.0
            strategy_name = r["exit_strategy_recommended"] or "DYNAMIC"
            try:
                strategy = ExitStrategy(strategy_name)
            except ValueError:
                strategy = ExitStrategy.TP_SL

            # 1. Récupère prix d'entrée (le bar d'open)
            entry_row = conn.execute(
                "SELECT mid FROM forces_snapshots WHERE snapshot_id = ? LIMIT 1",
                (r["snapshot_id"],),
            ).fetchone()

            # 2. Récupère prix futurs M5 (200 barres × 5min = ~16h)
            # Note : bar_time = epoch secondes (INTEGER), opened_at = ISO text.
            # Convertir opened_at → epoch pour comparaison.
            try:
                from datetime import datetime as _dt
                _opened_dt = _dt.fromisoformat(r["opened_at"].replace("Z", "+00:00"))
                _opened_epoch = int(_opened_dt.timestamp())
            except Exception:
                _opened_epoch = 0
            future_rows = conn.execute(
                """
                SELECT mid FROM forces_snapshots
                WHERE symbol = ? AND timeframe = 'M5'
                  AND bar_time > ?
                ORDER BY bar_time ASC
                LIMIT 200
                """,
                (r["symbol"], _opened_epoch),
            ).fetchall()

            is_artifact = False
            if entry_row and future_rows:
                # 2026-07-17 audit CEO fix : l'entry doit être le 1er M5 >= opened_at,
                # PAS le M15 du snapshot_id. Sinon gap M15→M5 fait hit SL/TP
                # instantanément (bug symétrie haussier/baissier).
                future_mids = [float(fr[0]) for fr in future_rows]
                entry_price = future_mids[0]
                # Sliding window pour trouver le 1er M5 ≥ entry du trade
                # (en réalité future_mids[0] est déjà après opened_at)
                # Recalcule entry sur le M5 le plus proche si dispo
                try:
                    sim = ExitSimulator(
                        strategy=strategy.value,
                        tp_pips=tp_pips,
                        sl_pips=sl_pips,
                        symbol=r["symbol"],
                    )
                    result = sim.simulate(
                        entry=entry_price,
                        direction=r["direction"],
                        future_mids=future_mids,
                    )
                    pips_simulated = result.pips
                    is_win = 1 if pips_simulated > 0 else 0
                    # P2 quantique : gestion active de position (break-even,
                    # partial close, time-exit). Kill switch défaut OFF (R2 :
                    # la résolution live reste ExitSimulator). Si ON, remplace
                    # le pips ExitSimulator par le pips managé sur la MÊME
                    # trajectoire. Nested try (R6) : un échec PM ne déclenche
                    # PAS le fallback artifact — on garde le pips ExitSimulator.
                    try:
                        from core.v9.position_manager import (
                            PositionManager, position_manager_enabled,
                        )
                        if position_manager_enabled():
                            pm_res = PositionManager().simulate(
                                entry=entry_price,
                                direction=r["direction"],
                                tp_pips=float(tp_pips),
                                sl_pips=float(sl_pips),
                                future_mids=future_mids,
                                symbol=r["symbol"],
                            )
                            pips_simulated = pm_res.pips
                            is_win = pm_res.is_win
                    except Exception as _pm_exc:
                        log.debug("close_open_trades: PM failed: %s", _pm_exc)
                except Exception:
                    is_artifact = True
                    pips_simulated = float(tp_pips) if is_win_db == 1 else -float(sl_pips)
                    is_win = is_win_db
            else:
                # Fallback : pas de prix futurs → pips fixes (artifact)
                is_artifact = True
                pips_simulated = float(tp_pips) if is_win_db == 1 else -float(sl_pips)
                is_win = is_win_db

            if is_artifact:
                artifact_count += 1

            # 2026-07-18 : appliquer les coûts de transaction au pips_simulated
            # Un trade gagnant perd le spread+commission+slippage, un perdant aussi
            try:
                from core.v9.transaction_costs import TransactionCosts
                _costs = TransactionCosts()
                _tx_costs = _costs.total_costs(
                    symbol=r["symbol"],
                    vol_regime=r["regime_type"] if r["regime_type"] else None,
                )
                pips_simulated = pips_simulated - _tx_costs
                # Re-déterminer is_win après coûts
                is_win = 1 if pips_simulated > 0 else 0
            except Exception:
                pass  # R6 : pas de crash sur les coûts

            conn.execute(
                """
                UPDATE paper_trades
                SET closed_at = ?, is_win = ?, pips_simulated = ?
                WHERE trade_id = ? AND closed_at IS NULL
                """,
                (now_utc, is_win, pips_simulated, r["trade_id"]),
            )
            closed += 1
            if is_win == 1:
                wins += 1
            else:
                losses += 1

        conn.commit()
        conn.close()

        # Stats globales
        total = closed_before + closed  # closed_before+closed (les ouvertures gérées par run_batch)
        closed_after = closed_before + closed

        if artifact_count > 0:
            log.warning(
                "close_open_trades: %d/%d trades en mode ARTIFACT (pas de prix futurs)",
                artifact_count, closed,
            )

        # Hook post-clôture (SOUL.md §4) : rafraîchit les métriques alpha et
        # déclenche l'auto-calibration si un multiple de 50 trades est franchi.
        # 2026-07-17 : seuil baissé de 100 à 50 pour accélérer l'apprentissage
        # multi-paires (6 paires = besoin de cycles plus fréquents).
        # 2026-07-17 motion CEO « orchestre et optimise au max » :
        #   lancé en BACKGROUND thread pour ne pas bloquer le batch.
        #   Gain mesuré : -12s sur un batch de 30 snapshots.
        # R6 : non-bloquant, ne remonte jamais d'exception.
        calib = None
        if closed and closed_after // 50 > closed_before // 50:
            calib = self._post_close_calibration_async()

        wr = wins / (wins + losses) * 100 if (wins + losses) else 0.0

        return {
            "closed": closed,
            "wins": wins,
            "losses": losses,
            "wr": round(wr, 1),
            "total_trades": total,
            "calibration_triggered": calib is not None,
            "calibration": calib,
            "artifact_count": artifact_count,  # 2026-07-17 audit CEO
        }

    def _post_close_calibration_async(self) -> dict[str, Any] | None:
        """Lance _post_close_calibration en background thread.

        2026-07-17 motion CEO « orchestre et optimise au max » :
        Ne bloque pas le batch. Le thread daemon termine même si le
        process principal s'arrête (R6 — best effort).
        """
        import threading

        def _run() -> None:
            try:
                self._post_close_calibration()
            except Exception as exc:
                log.debug("post_close_calibration thread failed: %s", exc)

        thread = threading.Thread(target=_run, daemon=True, name="v9-postcalib")
        thread.start()
        return {"async": True, "thread": thread.name}

    def _post_close_calibration(self) -> dict[str, Any] | None:
        """Rafraîchit les métriques alpha + lance un cycle d'auto-calibration.

        Déclenché tous les 100 trades clôturés (SOUL.md §4 — AUTO-CALIBRATOR).
        Entièrement défensif (R6) : toute erreur est avalée.
        """
        report: dict[str, Any] = {}
        # 1. Rafraîchit les métriques alpha (table principle_alpha_metrics).
        try:
            from core.v9.principle_alpha_engine import PrincipleAlphaEngine
            alpha = PrincipleAlphaEngine(db_path=self.db_path)
            alpha.invalidate_cache()
            n_persisted = 0
            for pid in alpha.list_principles():
                n_persisted += alpha.persist_metrics(pid)
            report["alpha_metrics_persisted"] = n_persisted
        except Exception as exc:
            log.debug("trade_engine: alpha refresh failed: %s", exc)

        # 2. Auto-calibration (recalibre seuils + profils, APPLIQUE les ajustements).
        try:
            from core.v9.auto_calibrator import (
                auto_calibrator_enabled,
                run_calibration_cycle,
            )
            if auto_calibrator_enabled():
                report["calibration"] = run_calibration_cycle(
                    db_path=self.db_path, notify=True, journal=True,  # notify=True = alerte Telegram
                    auto_apply=True,  # Mode writable (mandat CEO boucle fermee)
                )
        except Exception as exc:
            log.debug("trade_engine: auto-calibration failed: %s", exc)

        # 3. Auto-optimizer (grid search TP/SL tous les 100 trades).
        try:
            from core.v9.auto_optimizer import (
                auto_optimizer_enabled,
                run_optimization_cycle,
            )
            if auto_optimizer_enabled():
                report["optimizer"] = run_optimization_cycle(
                    db_path=self.db_path,
                )
        except Exception as exc:
            log.debug("trade_engine: auto-optimizer failed: %s", exc)

        return report or None

    def get_stats(self) -> dict[str, Any]:
        """Stats globales des paper trades."""
        conn = get_connection(self.db_path)
        try:
            total = conn.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
            wins = conn.execute("SELECT COUNT(*) FROM paper_trades WHERE is_win=1").fetchone()[0]
            losses = conn.execute(
                "SELECT COUNT(*) FROM paper_trades WHERE is_win=0 AND closed_at IS NOT NULL"
            ).fetchone()[0]
            open_t = conn.execute(
                "SELECT COUNT(*) FROM paper_trades WHERE closed_at IS NULL"
            ).fetchone()[0]
            total_pips = conn.execute(
                "SELECT COALESCE(SUM(pips_simulated), 0) FROM paper_trades WHERE closed_at IS NOT NULL"
            ).fetchone()[0]

            # By direction
            by_dir = {}
            for row in conn.execute(
                "SELECT direction, SUM(is_win) as w, COUNT(*) as n FROM paper_trades "
                "WHERE closed_at IS NOT NULL GROUP BY direction"
            ):
                w = row[1] or 0
                n = row[2] or 1
                by_dir[row[0]] = {"wins": w, "total": n, "wr": round(w / n * 100, 1)}
        finally:
            conn.close()

        wr = wins / (wins + losses) * 100 if (wins + losses) else 0.0
        return {
            "total": total,
            "open": open_t,
            "wins": wins,
            "losses": losses,
            "wr": round(wr, 1),
            "total_pips": round(total_pips, 1),
            "by_direction": by_dir,
        }

    # ── Helpers internes ──

    def _resolve_symbol_and_decision(
        self, snapshot_id: str,
    ) -> tuple[str | None, str | None]:
        """Résout (symbol, decision_id) pour un snapshot.

        `arbiter.consolidate()` ne renvoie ni symbol ni decision_id. On les
        lit depuis `decisions` (dernière décision live du snapshot). Fallback
        R6 : parse le symbole depuis le snapshot_id (format v9-SYMBOL-TF-...).
        Retourne (None, None) si tout échoue.
        """
        symbol: str | None = None
        decision_id: str | None = None
        try:
            conn = get_connection(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT decision_id, symbol FROM decisions "
                    "WHERE snapshot_id = ? ORDER BY timestamp DESC LIMIT 1",
                    (snapshot_id,),
                ).fetchone()
                if row is not None:
                    decision_id = row["decision_id"]
                    symbol = row["symbol"]
            finally:
                conn.close()
        except Exception:
            pass  # R6 — on retombe sur le parse snapshot_id ci-dessous.
        if not symbol and isinstance(snapshot_id, str):
            parts = snapshot_id.split("-")
            # v9-GBPUSD-M15-... → parts[1] = symbole 6 lettres.
            if len(parts) >= 2 and len(parts[1]) == 6 and parts[1].isalpha():
                symbol = parts[1].upper()
        return symbol, decision_id

    def _attach_bear_perception_shadow(
        self,
        result: dict[str, Any],
        snapshot_id: str,
        arbiter_result: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        """Évalue BearPerception en mode SHADOW et attache le diagnostic.

        Tâche 1 (mission baissier 2/2) — Phase A R25'. Entièrement additif
        (R2, clés préfixées `bear_perception_`) et défensif (R6 : toute
        exception → champs neutres, jamais de crash). N'altère PAS le flux,
        la direction ni le TP/SL : seule la clé `_would_*` documente ce que
        le moteur ferait en mode APPLY.

        Champs ajoutés à `result` :
          bear_perception_enabled   : bool (état du kill switch)
          bear_perception_signal    : dict | None (FastMovementSignal)
          bear_perception_would_skip: bool (should_skip_bearish hypothétique)
          bear_perception_would_exit: dict | None (compute_fast_exit si
                                       fast_move baissier détecté)
          bear_perception_status    : 'disabled' | 'evaluated' | 'error'
        """
        # Valeurs par défaut neutres (présentes même si kill switch OFF).
        result["bear_perception_enabled"] = False
        result["bear_perception_signal"] = None
        result["bear_perception_would_skip"] = False
        result["bear_perception_would_exit"] = None
        result["bear_perception_status"] = "disabled"

        try:
            from core.v9.v9_bear_perception import (
                BearAdaptiveStrategy,
                BearPerceptionCorrection,
                bear_perception_enabled,
            )
        except Exception as exc:  # import cassé → shadow inerte (R6).
            result["bear_perception_status"] = "error"
            result["bear_perception_reason"] = f"import: {exc}"
            return

        enabled = bear_perception_enabled()
        result["bear_perception_enabled"] = enabled
        # Kill switch OFF (défaut) : on n'évalue même pas. Zéro coût DB.
        if not enabled:
            return

        try:
            symbol, decision_id = self._resolve_symbol_and_decision(snapshot_id)
            if not symbol:
                result["bear_perception_status"] = "error"
                result["bear_perception_reason"] = "symbol_unresolved"
                return

            corrector = BearPerceptionCorrection(self.db_path)
            # decision_id peut être None → detect_fast_movement retombe sur
            # bar_time=now (fallback interne R6).
            signal = corrector.detect_fast_movement(
                symbol=str(symbol),
                decision_id=str(decision_id or snapshot_id),
            )
            result["bear_perception_signal"] = signal.to_dict()

            # market_ctx pour should_skip_bearish : reconstruit depuis le
            # contexte existant (aucune nouvelle requête). Les champs absents
            # (drift, h1_dir…) laissent should_skip_bearish fail-safe → False.
            market_ctx = {
                "drift_pips_per_day": context.get("drift_pips_per_day"),
                "h1_dir": context.get("h1_dir"),
                "regime_type": context.get("regime_type"),
                "regime_direction": context.get("regime_direction"),
                "vol_regime": context.get("vol_regime"),
            }
            strategy = BearAdaptiveStrategy()
            result["bear_perception_would_skip"] = bool(
                strategy.should_skip_bearish(arbiter_result, market_ctx)
            )

            # Exit adaptatif hypothétique : seulement si fast_move baissier.
            if signal.is_fast_move and signal.direction == "baissiere":
                # Vol proxy : 1 pips/min ≈ 3 pips ATR (cf. evaluate_decision).
                vol_proxy = round(signal.m1_signal_strength * 3.0, 2)
                result["bear_perception_would_exit"] = strategy.compute_fast_exit(
                    vol_pips=vol_proxy,
                )
            result["bear_perception_status"] = "evaluated"
        except Exception as exc:
            # R6 — aucune exception ne remonte : shadow best-effort.
            result["bear_perception_status"] = "error"
            result["bear_perception_reason"] = f"shadow_eval: {exc}"
            log.debug(
                "trade_engine: bear_perception shadow failed [%s]: %s",
                snapshot_id, exc,
            )

    def _build_context(self, snapshot_id: str, session: str) -> dict[str, Any]:
        """Construit le context pour RiskManager depuis la DB.

        Fix 2026-07-15 : les 3 requêtes précédentes filtraient sur une
        colonne `snapshot_id` inexistante dans `exploitability` (clé réelle :
        `window_id`) et `regime_snapshots` (clé réelle : `forces_snapshot_ref`,
        et `news_phase` n'a jamais existé dans ce schéma — voir
        `core/v9/regime_db.py`). `sqlite3.OperationalError` levée puis
        silencieusement avalée par le `except Exception: pass` ci-dessous :
        `context["news_phase"]` n'était donc JAMAIS peuplé (gate NEWS_SHOCK
        de `risk_manager.py` fail-open en continu) ; `window_status` restait
        toujours absent (fail-closed, sans conséquence observable mais
        incorrect) ; `regime_type` idem (non consommé par risk_manager
        actuellement, mais faux). Lit maintenant `decisions` (déjà écrite
        par `decision_logger.log()` avant l'appel de ce hook, cf.
        orchestrator.py) dont `regime_type`/`exploitability_id` sont déjà
        filtrés sur la devise de base du symbole (signal_generator.
        SymbolCurrencies) — et recalcule `news_phase` via `NewsContext`
        (même pattern que `v9_paper_trade_run._load_shared_context`)."""
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        context: dict[str, Any] = {"session_marche": session, "news_phase": "NEUTRE"}
        try:
            decision_row = conn.execute(
                "SELECT regime_type, exploitability_id, timestamp, symbol FROM decisions "
                "WHERE snapshot_id = ? ORDER BY timestamp DESC LIMIT 1",
                (snapshot_id,),
            ).fetchone()

            if decision_row is not None:
                context["regime_type"] = decision_row["regime_type"]
                # symbol : consommé par le PortfolioRiskManager (exposition nette
                # par devise) et par l'estimation des coûts de transaction.
                if decision_row["symbol"]:
                    context["symbol"] = decision_row["symbol"]

                if decision_row["exploitability_id"]:
                    expl = conn.execute(
                        "SELECT statut FROM exploitability WHERE exploitability_id = ?",
                        (decision_row["exploitability_id"],),
                    ).fetchone()
                    if expl is not None:
                        statut = expl["statut"]
                        context["window_status"] = (
                            "exploitable" if statut in ("exploitable", "watchlist")
                            else (statut or "absente")
                        )

                ts_str = decision_row["timestamp"]
                if ts_str:
                    from core.v9.news_context import NewsContext  # noqa: PLC0415
                    ts_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    context["news_phase"] = NewsContext().assess(ts_dt).get(
                        "news_phase", "NEUTRE"
                    )
        except Exception:
            pass
        finally:
            conn.close()
        return context

    def _load_full_context(self, snapshot_id: str) -> dict[str, Any] | None:
        """Charge le contexte cognitif complet (scene/behavior/regime) d'un
        snapshot pour le DynamicRiskManager (Phase 13.3).

        Lit `decisions.contexte_complet_json` (zlib) et le décompresse via
        `load_contexte_complet`. Défensif (R6) : retourne None en cas d'échec.
        """
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT contexte_complet_json FROM decisions "
                "WHERE snapshot_id = ? AND contexte_complet_json IS NOT NULL "
                "ORDER BY timestamp DESC LIMIT 1",
                (snapshot_id,),
            ).fetchone()
            if row is None or not row["contexte_complet_json"]:
                return None
            from core.v9.decision_logger import load_contexte_complet
            return load_contexte_complet(row["contexte_complet_json"])
        except Exception:
            return None
        finally:
            conn.close()

    def _get_open_trades(self) -> list[dict]:
        """Liste les trades actuellement ouverts.

        2026-07-18 (P0 quantique) : ajoute `symbol` via LEFT JOIN decisions
        pour alimenter le PortfolioRiskManager (exposition nette par devise,
        corrélation entre paires). paper_trades n'a pas de colonne symbol ;
        elle est reconstruite depuis la décision liée au snapshot. Le JOIN
        reste peu coûteux (exécuté une fois par batch, préchargé dans
        `_batch_open_trades`). R6 : fallback sans symbol si le JOIN échoue.
        """
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            try:
                rows = conn.execute(
                    "SELECT pt.trade_id, pt.direction, pt.pips_simulated, "
                    "       d.symbol AS symbol "
                    "FROM paper_trades pt "
                    "LEFT JOIN decisions d ON d.snapshot_id = pt.snapshot_id "
                    "WHERE pt.closed_at IS NULL "
                    "GROUP BY pt.trade_id"
                ).fetchall()
            except Exception:
                rows = conn.execute(
                    "SELECT trade_id, direction, pips_simulated FROM paper_trades "
                    "WHERE closed_at IS NULL"
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def _recent_returns_pips(self, symbol: str | None, limit: int) -> list[float]:
        """Returns récents (pips_simulated) des N derniers paper_trades fermés
        d'une paire — base d'estimation du CVaR (Chantier B). R6 : jamais
        d'exception, liste vide si data absente."""
        if not symbol:
            return []
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT pt.pips_simulated FROM paper_trades pt "
                "JOIN decisions d ON d.snapshot_id = pt.snapshot_id "
                "WHERE pt.closed_at IS NOT NULL AND pt.pips_simulated IS NOT NULL "
                "  AND d.symbol = ? "
                "ORDER BY pt.closed_at DESC LIMIT ?",
                (symbol, int(limit)),
            ).fetchall()
            return [float(r[0]) for r in rows if r[0] is not None]
        except Exception:
            return []
        finally:
            conn.close()

    def _trade_already_open(self, snapshot_id: str, direction: str | None) -> bool:
        """Vérifie l'idempotence — un snapshot n'est tradé qu'une seule fois.

        Fix P0 2026-07-20 : auparavant la garde filtrait `closed_at IS NULL`,
        donc elle ne détectait que les trades ENCORE ouverts. Un snapshot dont
        le trade avait été clôturé redevenait éligible → le hook live
        (post_decision_hook, une TradeEngine fraîche par snapshot) le
        ré-ouvrait à chaque passage, empilant jusqu'à 7 paper_trades clôturés
        sur le même snapshot_id (catastrophe 17/07, récidive 19-20/07).
        On compte désormais TOUT trade du couple (snapshot_id, direction),
        ouvert OU fermé : un snapshot déjà tradé n'est jamais re-tradé. Le nom
        de la méthode est conservé (rétro-compat des stubs de test) ; la
        sémantique est « already traded », pas seulement « already open ».
        """
        if direction is None:
            return True
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM paper_trades "
                "WHERE snapshot_id = ? AND direction = ?",
                (snapshot_id, direction),
            ).fetchone()
            return row[0] > 0
        finally:
            conn.close()

    def _fetch_signal_recommendation(self, snapshot_id: str) -> dict[str, Any]:
        """Lit tp_pips/sl_pims/exit_strategy depuis la table signals."""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT exit_strategy_recommended, tp_pips_recommended, "
                "sl_pips_recommended FROM signals WHERE snapshot_id = ? "
                "ORDER BY rowid DESC LIMIT 1",
                (snapshot_id,),
            ).fetchone()
            if row:
                return {
                    "exit_strategy_recommended": row[0],
                    "tp_pips_recommended": row[1],
                    "sl_pips_recommended": row[2],
                }
        except Exception:
            pass
        finally:
            conn.close()
        return {}

    def _fetch_recent_snapshots(self, limit: int) -> list[str]:
        """Récupère les N derniers snapshot_id distincts avec décisions live.

        2026-07-17 motion CEO « go débloquer tout fait tout pour go » :
        élargi pour inclure aussi les décisions résolues (is_win NOT NULL),
        car le pipeline offline peut résoudre une décision sans paper-trade
        correspondant.

        2026-07-17 motion CEO « continue optimiser au max » :
        Exclut les snapshots déjà tradés ET fermés (ça évitait qu'on
        rouvre indéfiniment les mêmes). Si un trade est OUVERT pour ce
        snapshot, on le saute (idempotence) ; si tous les trades sont
        FERMÉS, on peut en ouvrir un nouveau (backtest).
        """
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT d.snapshot_id
                FROM decisions d
                LEFT JOIN (
                    SELECT snapshot_id,
                           SUM(CASE WHEN closed_at IS NULL THEN 1 ELSE 0 END) AS open_count,
                           COUNT(*) AS total_count
                    FROM paper_trades
                    GROUP BY snapshot_id
                ) pt ON pt.snapshot_id = d.snapshot_id
                WHERE d.action = 'preparer_entree'
                  AND d.source_type = 'live'
                  AND (pt.open_count IS NULL OR pt.open_count = 0)
                GROUP BY d.snapshot_id
                ORDER BY MAX(d.timestamp) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [r[0] for r in rows]
        finally:
            conn.close()


# ── Hook pour l'orchestrator ──

def post_decision_hook(snapshot_id: str, db_path: Path | None = None) -> dict[str, Any] | None:
    """Hook appelé par l'orchestrator après decision_logger.

    Si la décision est 'preparer_entree' et que le kill switch est ON,
    lance le trade_engine sur ce snapshot. Non-bloquant (R6).

    Retourne le résultat du trade_engine, ou None si désactivé/erreur.
    """
    if not _trade_engine_enabled():
        return None

    try:
        engine = TradeEngine(db_path=db_path)
        return engine.process(snapshot_id)
    except Exception as exc:
        log.debug("trade_engine: post_decision_hook failed [%s]: %s", snapshot_id, exc)
        return None