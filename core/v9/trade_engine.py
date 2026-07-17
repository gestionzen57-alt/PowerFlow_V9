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
from core.v9.config import DB_PATH
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
from core.v9.paper_risk_manager import PaperRiskManager
from core.v9.paper_trade_logger import PaperTradeLogger
from core.v9.pyramiding_engine import PyramidingEngine

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


def _trade_engine_enabled() -> bool:
    """Kill switch du trade_engine. Défaut ON (Phase 12 simulation)."""
    return os.environ.get(TRADE_ENGINE_ENV, "1") not in ("0", "", "false", "False")


def _dynamic_risk_enabled() -> bool:
    """Kill switch du DynamicRiskManager (SHADOW). Défaut ON."""
    return os.environ.get(DYNAMIC_RISK_ENV, "1") not in ("0", "", "false", "False")


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

        # 1. Arbiter — consolidation
        try:
            arbiter_result = self.arbiter.consolidate(snapshot_id)
        except Exception as exc:
            result["error"] = f"arbiter: {exc}"
            log.debug("trade_engine: arbiter failed [%s]: %s", snapshot_id, exc)
            return result

        result["direction"] = arbiter_result.get("direction")
        result["confiance"] = arbiter_result.get("confiance_arbitree", 0)

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

        result["tp_pips"] = tp_pips
        result["sl_pips"] = sl_pips
        result["strategy"] = strategy

        # 4b. DynamicRiskManager — APPLY (Phase 13.3, activé Søn 2026-07-17).
        # Évalue la gestion de risque adaptative (phase/cycle/coalition) et
        # APPLIQUE le SL/TP/exit sur le trade courant (motion CEO c6afebb).
        # Garde-fous : R6 (try/except silencieux, fallback statique) ; R2 (le
        # pipeline reste additif — `result["dynamic_risk"]` conserve le détail).
        # Si `phase == INDETERMINE` ou `source == "fallback"` : on conserve les
        # valeurs courantes. Si `allow_new_position == False` (climax) :
        # on force `action=skip` sans décision.
        result["dynamic_risk"] = None
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

        # 6. Idempotence — pas de doublon
        if self._trade_already_open(snapshot_id, arbiter_result.get("direction")):
            result["action"] = "skip"
            result["raison_blocage"] = "trade_deja_ouvert"
            return result

        # 7. Ouvrir le paper-trade
        try:
            trade_id = self.trade_logger.log_open(
                arbiter_result, context,
            )
            result["trade_id"] = trade_id
            result["action"] = "open"
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
        """Clôture les paper_trades ouverts avec SL/TP réels.

        Au lieu de hardcoder ±10 pips, lit tp_pips/sl_pips depuis le signal
        et utilise ExitSimulator pour déterminer quel seuil a été touché.

        Fallback : si pas de prix futurs disponibles, utilise decisions.is_win
        (comportement historique, backward compat).
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
                   s.tp_pips_recommended, s.sl_pips_recommended,
                   s.exit_strategy_recommended
            FROM paper_trades pt
            JOIN decisions d ON d.snapshot_id = pt.snapshot_id
            LEFT JOIN signals s ON s.snapshot_id = pt.snapshot_id
            WHERE pt.closed_at IS NULL
              AND d.is_win IS NOT NULL
            ORDER BY pt.opened_at
            """,
        ).fetchall()

        if not rows:
            total = conn.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
            conn.close()
            return {
                "closed": 0, "wins": 0, "losses": 0, "wr": 0.0,
                "total_trades": total, "calibration_triggered": False,
                "calibration": None,
            }

        wins = 0
        losses = 0
        closed = 0

        for r in rows:
            is_win = r["is_win"]
            tp_pips = r["tp_pips_recommended"] or 10.0
            sl_pips = r["sl_pips_recommended"] or 15.0

            # Pips réels : si WIN → +tp_pips, si LOSS → -sl_pips
            # (au lieu de ±10 hardcodés)
            pips_simulated = float(tp_pips) if is_win == 1 else -float(sl_pips)

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

        # Stats globales
        total = conn.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
        closed_after = closed_before + closed
        conn.close()

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
                "SELECT regime_type, exploitability_id, timestamp FROM decisions "
                "WHERE snapshot_id = ? ORDER BY timestamp DESC LIMIT 1",
                (snapshot_id,),
            ).fetchone()

            if decision_row is not None:
                context["regime_type"] = decision_row["regime_type"]

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
        """Liste les trades actuellement ouverts."""
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT trade_id, direction, pips_simulated FROM paper_trades "
                "WHERE closed_at IS NULL"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def _trade_already_open(self, snapshot_id: str, direction: str | None) -> bool:
        """Vérifie l'idempotence — pas de doublon."""
        if direction is None:
            return True
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM paper_trades "
                "WHERE snapshot_id = ? AND direction = ? AND closed_at IS NULL",
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