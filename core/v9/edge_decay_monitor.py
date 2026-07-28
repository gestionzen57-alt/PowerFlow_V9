"""EdgeDecayMonitor — Détection proactive de la dégradation d'edge par principe.

Surveille en continu WR, expectancy, edge par (principe × session × régime)
et déclenche des alertes + actions automatiques (blacklist, démotion, observation).

Doctrine : R2 additif, R6 défensif, R18 code pur, R25'' auto-démotion, R30 boucle fermée.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.config import DB_PATH, PRINCIPLE_ACTIVE_IDS, ROOT_DIR
from core.v9.db_schema import get_connection
from core.v9.kill_switches import get as ks_get

logger = logging.getLogger(__name__)

from core.v9.exit_simulator import infer_session_from_hour  # noqa: E402

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

EDGE_DECAY_ENABLED_ENV = "V9_EDGE_DECAY_MONITOR_ENABLED"

# Fenêtres d'analyse (en nombre de trades résolus)
WINDOWS = {
    "short": 50,    # récent - détection rapide
    "medium": 200,  # baseline stable
    "long": 1000,   # référence historique
}

# Seuils d'alerte
THRESHOLDS = {
    "wr_drop_short_vs_medium": 0.10,      # -10% WR court vs moyen → WARNING
    "wr_drop_medium_vs_long": 0.15,       # -15% WR moyen vs long → CRITICAL
    "expectancy_sign_flip": True,         # expectancy passe négatif → CRITICAL
    "min_trades_per_window": 30,          # minimum trades pour valider fenêtre
    "consecutive_losses_alert": 5,        # pertes consécutives → WARNING
    "sharpe_degradation": 0.5,            # Sharpe drop > 0.5 → WARNING
}

# Actions automatiques par niveau
AUTO_ACTIONS = {
    "WARNING": ["increase_observation", "notify_telegram"],
    "CRITICAL": ["blacklist_session_regime", "demote_principle", "notify_telegram", "halt_new_positions"],
}

# Fichier d'état
STATE_PATH = ROOT_DIR / "config" / "v9_edge_decay_state.json"

# ──────────────────────────────────────────────────────────────────────────────
# Kill switch
# ──────────────────────────────────────────────────────────────────────────────

def edge_decay_monitor_enabled() -> bool:
    return ks_get(EDGE_DECAY_ENABLED_ENV, "1") == "1"


# ──────────────────────────────────────────────────────────────────────────────
# Structures de données
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class WindowStats:
    """Stats pour une fenêtre temporelle."""
    n_trades: int = 0
    n_wins: int = 0
    total_pips: float = 0.0
    sum_pips_sq: float = 0.0
    max_consecutive_losses: int = 0
    current_consecutive_losses: int = 0
    max_dd_pips: float = 0.0
    peak_pips: float = 0.0
    
    @property
    def wr(self) -> float:
        return self.n_wins / max(self.n_trades, 1)
    
    @property
    def expectancy(self) -> float:
        return self.total_pips / max(self.n_trades, 1)
    
    @property
    def sharpe_like(self) -> float:
        if self.n_trades < 2:
            return 0.0
        mean = self.expectancy
        variance = (self.sum_pips_sq / self.n_trades) - (mean * mean)
        std = variance ** 0.5 if variance > 0 else 0.0
        return mean / max(std, 1e-6)
    
    def to_dict(self) -> dict:
        return {
            "n_trades": self.n_trades,
            "wr": round(self.wr, 4),
            "expectancy": round(self.expectancy, 2),
            "sharpe_like": round(self.sharpe_like, 3),
            "max_consecutive_losses": self.max_consecutive_losses,
            "max_dd_pips": round(self.max_dd_pips, 1),
        }


@dataclass
class Alert:
    """Alerte de dégradation d'edge."""
    level: str  # "WARNING" | "CRITICAL"
    principle_id: str
    symbol: str
    session: str
    regime_type: str
    message: str
    action: str
    short_stats: dict
    medium_stats: dict
    long_stats: dict
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EdgeDecayState:
    """État persistant du monitor."""
    version: str = "1.0"
    last_check_ts: float = 0.0
    last_check_iso: str = ""
    alerts_history: list[dict] = field(default_factory=list)
    blacklisted_contexts: set = field(default_factory=set)  # tuples (principle, session, regime)
    demoted_principles: set = field(default_factory=set)
    observation_mode: dict = field(default_factory=dict)  # principle -> {"since": ts, "reason": str}
    
    def to_dict(self) -> dict:
        d = asdict(self)
        d["blacklisted_contexts"] = list(self.blacklisted_contexts)
        d["demoted_principles"] = list(self.demoted_principles)
        return d
    
    @classmethod
    def load(cls) -> "EdgeDecayState":
        if STATE_PATH.exists():
            try:
                data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                data["blacklisted_contexts"] = set(tuple(c) for c in data.get("blacklisted_contexts", []))
                data["demoted_principles"] = set(data.get("demoted_principles", []))
                return cls(**data)
            except Exception:
                pass
        return cls()
    
    def save(self) -> None:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATE_PATH)


# ──────────────────────────────────────────────────────────────────────────────
# Monitor principal
# ──────────────────────────────────────────────────────────────────────────────

class EdgeDecayMonitor:
    """Moniteur de dégradation d'edge par principe × session × régime."""
    
    def __init__(self, db_path: Path | str | None = None, auto_actions: bool = False):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.state = EdgeDecayState.load()
        # R25' strict : auto_actions=False par défaut. Activer seulement via
        # motion CEO explicite tracée dans DECISIONS_LOG.md.
        self._auto_actions_enabled = auto_actions
    
    def check_all_principles(self) -> list[Alert]:
        """Vérifie tous les principes ACTIVE et retourne les alertes.

        Auto-actions (blacklist, démote, halt) sont calculées et tracées dans
        l'état (`EdgeDecayState`) MAIS NON EXÉCUTÉES par défaut — la motion CEO
        explicite est requise pour R25' strict. Le runner `v9_edge_decay_monitor_run`
        appelle cette méthode en mode read-only (skip_blacklist_actions=True).
        Pour activer l'auto-exécution : `EdgeDecayMonitor(..., auto_actions=True)`
        ou motion CEO explicite dans `DECISIONS_LOG.md`.
        """
        if not edge_decay_monitor_enabled():
            return []

        alerts: list[Alert] = []

        # Une seule query globale (snapshot-level) au lieu d'1 JOIN par (principle, regime)
        # Évite le ×N requêtes sur principle_evaluations 8M rows.
        trades = self._fetch_recent_trades_single_query()

        for principle_id in PRINCIPLE_ACTIVE_IDS:
            # Skip si déjà en observation mode (laissé le temps de récupérer)
            if principle_id in self.state.observation_mode:
                continue

            principle_alerts = self._check_principle(principle_id, trades)
            alerts.extend(principle_alerts)

            # Tracer les actions auto SANS les exécuter (R25' strict)
            for alert in principle_alerts:
                if alert.level == "CRITICAL" and self._auto_actions_enabled:
                    self._execute_auto_actions(alert)
                elif alert.level == "CRITICAL":
                    # Mode read-only : juste logger l'intention (stderr, pas JSON)
                    print(
                        f"EdgeDecay: [DRY-RUN] {alert.action} {alert.principle_id} | "
                        f"{alert.session} | {alert.regime_type} — motion CEO requise",
                        file=sys.stderr,
                    )

        # Mettre à jour l'état
        self.state.last_check_ts = time.time()
        self.state.last_check_iso = datetime.fromtimestamp(
            self.state.last_check_ts, tz=timezone.utc
        ).isoformat()

        # Garder seulement les 100 dernières alertes
        for alert in alerts:
            self.state.alerts_history.append(alert.to_dict())
        self.state.alerts_history = self.state.alerts_history[-100:]

        self.state.save()

        return alerts

    def _check_principle(
        self, principle_id: str, trades: dict | None = None
    ) -> list[Alert]:
        """Vérifie un principe sur tous les (session, régime) actifs.

        Si `trades` est fourni (par check_all_principles), évite la re-query.
        Sinon (appel direct), fait la query single-shot localement.
        """
        alerts = []

        if trades is None:
            trades = self._fetch_recent_trades_single_query()

        # trades est indexé par (principle_id, session, regime) -> list[(is_win, pips, ts)]

        for (pid, session, regime), rows in trades.items():
            if pid != principle_id:
                continue
            # Skip si déjà blacklisté
            if (principle_id, session, regime) in self.state.blacklisted_contexts:
                continue

            stats = self._stats_from_rows(rows)
            if not self._has_min_trades(stats):
                continue

            principle_alerts = self._evaluate_degradation(
                principle_id, session, regime, stats
            )
            alerts.extend(principle_alerts)

        return alerts

    def _fetch_recent_trades_single_query(self) -> dict[tuple[str, str, str], list[tuple[int, float, str]]]:
        """Query globale : tous les trades résolus DYNAMIC récents 30j, par (principle, session, regime).

        Évite le ×N requêtes JOIN qui timeout sur DB 5.7GB.
        Retourne dict indexé par (principle_id, session, regime) -> list[(is_win, pips, ts)].
        """
        conn = get_connection(self.db_path)
        try:
            # Snapshot-level query (decisions = 100k rows = OK) avec principle_id
            # via JOIN sur principle_evaluations mais on prend que les decisions
            # récentes (filtre timestamp d'abord), puis on JOIN.
            rows = conn.execute("""
                SELECT pe.principle_id, d.is_win, d.resolution_pips, d.timestamp, d.regime_type
                FROM decisions d
                JOIN principle_evaluations pe
                  ON pe.snapshot_id = d.snapshot_id AND pe.triggered = 1
                WHERE d.is_win IS NOT NULL
                  AND d.resolution_strategy = 'DYNAMIC'
                  AND d.timestamp > datetime('now', '-30 days')
                ORDER BY d.timestamp DESC
                LIMIT 50000
            """).fetchall()
        finally:
            conn.close()

        # Grouper en Python
        def _row_session(ts_iso) -> str:
            try:
                if isinstance(ts_iso, (int, float)):
                    hour_utc = datetime.fromtimestamp(float(ts_iso), tz=timezone.utc).hour
                else:
                    hour_utc = datetime.fromisoformat(str(ts_iso).replace("Z", "+00:00")).hour
                return infer_session_from_hour(hour_utc)
            except Exception:
                return "unknown"

        out: dict[tuple[str, str, str], list[tuple[int, float, str]]] = {}
        for r in rows:
            pid = r[0]
            is_win = r[1]
            pips = r[2] or 0.0
            ts_iso = r[3]
            regime = r[4] or "NEUTRE"
            session = _row_session(ts_iso)
            key = (pid, session, regime)
            out.setdefault(key, []).append((is_win, pips, ts_iso))
        return out

    def _stats_from_rows(self, rows: list[tuple[int, float, str]]) -> dict[str, WindowStats]:
        """Calcule stats pour les 3 fenêtres depuis rows triés DESC par timestamp."""
        all_trades = [(is_win, pips) for is_win, pips, _ in rows]
        stats = {}
        for window_name, window_size in WINDOWS.items():
            trades = all_trades[:window_size]  # déjà triés DESC
            stats[window_name] = self._calculate_stats(trades)
        return stats
    
    def _get_active_contexts(self, principle_id: str) -> list[tuple[str, str]]:
        """Récupère les (session, regime) où le principe a des trades résolus récents.

        Optimisation : LIMIT 5000 par principe (suffisant pour échantillonner
        30 jours sur 41 principes). Sans LIMIT, le scan principle_evaluations
        × decisions (7M × 100k) sur DB 5.7GB dépasse 5 min.
        """
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute("""
                SELECT DISTINCT
                    d.timestamp as ts_iso,
                    d.regime_type
                FROM principle_evaluations pe
                JOIN decisions d ON d.snapshot_id = pe.snapshot_id
                WHERE pe.principle_id = ?
                  AND pe.triggered = 1
                  AND d.is_win IS NOT NULL
                  AND d.resolution_strategy = 'DYNAMIC'
                  AND d.timestamp > datetime('now', '-30 days')
                ORDER BY d.timestamp DESC
                LIMIT 5000
            """, (principle_id,)).fetchall()

            # Helper pour inférer session depuis timestamp ISO
            contexts = []
            for row in rows:
                ts_iso = row[0]
                regime = row[1] or "NEUTRE"
                try:
                    # timestamp peut être ISO 8601 ou epoch int (legacy)
                    if isinstance(ts_iso, (int, float)):
                        hour_utc = datetime.fromtimestamp(float(ts_iso), tz=timezone.utc).hour
                    else:
                        hour_utc = datetime.fromisoformat(str(ts_iso).replace("Z", "+00:00")).hour
                    session = infer_session_from_hour(hour_utc)
                except Exception:
                    session = "unknown"
                contexts.append((session, regime))
            return contexts
        finally:
            conn.close()

    def _compute_window_stats(self, principle_id: str, session: str, regime: str) -> dict[str, WindowStats]:
        """Calcule les stats pour les 3 fenêtres."""
        conn = get_connection(self.db_path)
        try:
            # Récupérer tous les trades résolus pour ce contexte, ordonnés par temps
            rows = conn.execute("""
                SELECT d.is_win, d.resolution_pips, d.timestamp
                FROM principle_evaluations pe
                JOIN decisions d ON d.snapshot_id = pe.snapshot_id
                WHERE pe.principle_id = ?
                  AND pe.triggered = 1
                  AND d.is_win IS NOT NULL
                  AND d.resolution_strategy = 'DYNAMIC'
                  AND d.regime_type = ?
                ORDER BY d.timestamp DESC
                LIMIT 5000
            """, (principle_id, regime)).fetchall()

            # Filtrer par session en post-process (pas d'UDF SQL dispo)
            def _row_session(r) -> str:
                ts_iso = r[2]
                try:
                    if isinstance(ts_iso, (int, float)):
                        hour_utc = datetime.fromtimestamp(float(ts_iso), tz=timezone.utc).hour
                    else:
                        hour_utc = datetime.fromisoformat(str(ts_iso).replace("Z", "+00:00")).hour
                    return infer_session_from_hour(hour_utc)
                except Exception:
                    return "unknown"

            rows = [r for r in rows if _row_session(r) == session]

            # Calculer stats par fenêtre (en prenant les N derniers trades)
            all_trades = [(r[0], r[1] or 0.0) for r in rows]
            
            stats = {}
            for window_name, window_size in WINDOWS.items():
                trades = all_trades[-window_size:] if len(all_trades) >= window_size else all_trades
                stats[window_name] = self._calculate_stats(trades)
            
            return stats
        finally:
            conn.close()
    
    def _calculate_stats(self, trades: list[tuple[int, float]]) -> WindowStats:
        """Calcule stats depuis liste de (is_win, pips)."""
        if not trades:
            return WindowStats()
        
        ws = WindowStats()
        ws.n_trades = len(trades)
        
        consec_losses = 0
        max_consec = 0
        peak = 0.0
        running_pips = 0.0
        max_dd = 0.0
        
        for is_win, pips in trades:
            ws.total_pips += pips
            ws.sum_pips_sq += pips * pips
            
            if is_win:
                ws.n_wins += 1
                consec_losses = 0
            else:
                consec_losses += 1
                max_consec = max(max_consec, consec_losses)
            
            running_pips += pips
            peak = max(peak, running_pips)
            dd = peak - running_pips
            max_dd = max(max_dd, dd)
        
        ws.max_consecutive_losses = max_consec
        ws.current_consecutive_losses = consec_losses
        ws.peak_pips = peak
        ws.max_dd_pips = max_dd
        
        return ws
    
    def _has_min_trades(self, stats: dict[str, WindowStats]) -> bool:
        """Vérifie qu'on a assez de trades dans la fenêtre medium (baseline)."""
        return stats["medium"].n_trades >= THRESHOLDS["min_trades_per_window"]
    
    def _evaluate_degradation(
        self, 
        principle_id: str, 
        session: str, 
        regime: str, 
        stats: dict[str, WindowStats]
    ) -> list[Alert]:
        """Évalue les 3 tests de dégradation."""
        alerts = []
        short = stats["short"]
        medium = stats["medium"]
        long = stats["long"]
        
        # TEST 1: WR drop court vs moyen
        if short.n_trades >= THRESHOLDS["min_trades_per_window"]:
            wr_drop = medium.wr - short.wr
            if wr_drop > THRESHOLDS["wr_drop_short_vs_medium"] and medium.wr > 0:
                alerts.append(Alert(
                    level="WARNING",
                    principle_id=principle_id,
                    symbol="",  # sera rempli par appelant si nécessaire
                    session=session,
                    regime_type=regime,
                    message=(
                        f"WR drop {medium.wr:.1%}→{short.wr:.1%} "
                        f"(Δ={wr_drop:.1%} > {THRESHOLDS['wr_drop_short_vs_medium']:.0%}) "
                        f"sur {short.n_trades} trades récents"
                    ),
                    action="increase_observation",
                    short_stats=short.to_dict(),
                    medium_stats=medium.to_dict(),
                    long_stats=long.to_dict(),
                ))
        
        # TEST 2: WR drop moyen vs long (dégradation structurelle)
        if long.n_trades >= THRESHOLDS["min_trades_per_window"]:
            wr_drop = long.wr - medium.wr
            if wr_drop > THRESHOLDS["wr_drop_medium_vs_long"] and long.wr > 0:
                alerts.append(Alert(
                    level="CRITICAL",
                    principle_id=principle_id,
                    symbol="",
                    session=session,
                    regime_type=regime,
                    message=(
                        f"WR dégradation structurelle {long.wr:.1%}→{medium.wr:.1%} "
                        f"(Δ={wr_drop:.1%} > {THRESHOLDS['wr_drop_medium_vs_long']:.0%}) "
                        f"sur {medium.n_trades} trades"
                    ),
                    action="demote_principle",
                    short_stats=short.to_dict(),
                    medium_stats=medium.to_dict(),
                    long_stats=long.to_dict(),
                ))
        
        # TEST 3: Expectancy sign flip
        if medium.expectancy > 0 and short.expectancy < 0:
            alerts.append(Alert(
                level="CRITICAL",
                principle_id=principle_id,
                symbol="",
                session=session,
                regime_type=regime,
                message=(
                    f"Expectancy sign flip: {medium.expectancy:.1f}→{short.expectancy:.1f} pips "
                    f"(moyen→court)"
                ),
                action="blacklist_session_regime",
                short_stats=short.to_dict(),
                medium_stats=medium.to_dict(),
                long_stats=long.to_dict(),
            ))
        
        # TEST 4: Pertes consécutives excessives
        if short.current_consecutive_losses >= THRESHOLDS["consecutive_losses_alert"]:
            alerts.append(Alert(
                level="WARNING",
                principle_id=principle_id,
                symbol="",
                session=session,
                regime_type=regime,
                message=(
                    f"{short.current_consecutive_losses} pertes consécutives "
                    f"(seuil={THRESHOLDS['consecutive_losses_alert']})"
                ),
                action="increase_observation",
                short_stats=short.to_dict(),
                medium_stats=medium.to_dict(),
                long_stats=long.to_dict(),
            ))
        
        # TEST 5: Sharpe degradation
        if long.sharpe_like > 0 and medium.sharpe_like > 0:
            sharpe_drop = long.sharpe_like - medium.sharpe_like
            if sharpe_drop > THRESHOLDS["sharpe_degradation"]:
                alerts.append(Alert(
                    level="WARNING",
                    principle_id=principle_id,
                    symbol="",
                    session=session,
                    regime_type=regime,
                    message=(
                        f"Sharpe drop {long.sharpe_like:.2f}→{medium.sharpe_like:.2f} "
                        f"(Δ={sharpe_drop:.2f} > {THRESHOLDS['sharpe_degradation']})"
                    ),
                    action="increase_observation",
                    short_stats=short.to_dict(),
                    medium_stats=medium.to_dict(),
                    long_stats=long.to_dict(),
                ))
        
        return alerts
    
    def _execute_auto_actions(self, alert: Alert) -> None:
        """Exécute les actions automatiques pour une alerte CRITICAL."""
        principle = alert.principle_id
        session = alert.session
        regime = alert.regime_type
        action = alert.action
        
        if action == "blacklist_session_regime":
            self.state.blacklisted_contexts.add((principle, session, regime))
            logger.warning(f"EdgeDecay: BLACKLISTED {principle} | {session} | {regime}")
            
            # Notifier auto_calibrator pour qu'il prenne en compte
            self._notify_auto_calibrator_blacklist(principle, session, regime)
        
        elif action == "demote_principle":
            self.state.demoted_principles.add(principle)
            logger.warning(f"EdgeDecay: DEMOTED {principle} (structurelle)")
            
            # Écrire dans calibration_overrides pour que auto_calibrator le démotte
            self._write_demotion_override(principle)
        
        elif action == "halt_new_positions":
            # Activer DD Protector halt si pas déjà
            self._trigger_dd_protector_halt(principle, session, regime)
        
        elif action == "increase_observation":
            self.state.observation_mode[principle] = {
                "since": time.time(),
                "reason": alert.message,
                "session": session,
                "regime": regime,
            }
            logger.info(f"EdgeDecay: OBSERVATION MODE {principle} - {alert.message}")
    
    def _notify_auto_calibrator_blacklist(self, principle: str, session: str, regime: str) -> None:
        """Écrit une entrée dans calibration_overrides pour blacklister."""
        overrides_path = ROOT_DIR / "config" / "calibration_overrides.json"
        try:
            overrides = json.loads(overrides_path.read_text(encoding="utf-8")) if overrides_path.exists() else {}
            bl = overrides.get("blacklisted_contexts", [])
            entry = {"principle_id": principle, "session": session, "regime": regime, "reason": "edge_decay"}
            if entry not in bl:
                bl.append(entry)
            overrides["blacklisted_contexts"] = bl
            overrides["updated_at"] = datetime.now(timezone.utc).isoformat()
            tmp = overrides_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(overrides, indent=2), encoding="utf-8")
            tmp.replace(overrides_path)
        except Exception as e:
            logger.error(f"Failed to notify auto_calibrator: {e}")
    
    def _write_demotion_override(self, principle: str) -> None:
        """Force la démotion via calibration_overrides."""
        overrides_path = ROOT_DIR / "config" / "calibration_overrides.json"
        try:
            overrides = json.loads(overrides_path.read_text(encoding="utf-8")) if overrides_path.exists() else {}
            demoted = overrides.get("demoted_principles", [])
            if principle not in demoted:
                demoted.append(principle)
            overrides["demoted_principles"] = demoted
            overrides["updated_at"] = datetime.now(timezone.utc).isoformat()
            tmp = overrides_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(overrides, indent=2), encoding="utf-8")
            tmp.replace(overrides_path)
        except Exception as e:
            logger.error(f"Failed to write demotion override: {e}")
    
    def _trigger_dd_protector_halt(self, principle: str, session: str, regime: str) -> None:
        """Active le DD Protector en mode halt pour ce contexte."""
        # Écrire dans un fichier lu par DD Protector
        dd_state_path = ROOT_DIR / "config" / "v9_dd_protector_state.json"
        try:
            state = json.loads(dd_state_path.read_text(encoding="utf-8")) if dd_state_path.exists() else {}
            halts = state.get("context_halts", [])
            entry = {"principle": principle, "session": session, "regime": regime, "ts": time.time()}
            if entry not in halts:
                halts.append(entry)
            state["context_halts"] = halts
            tmp = dd_state_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
            tmp.replace(dd_state_path)
        except Exception:
            pass
    
    def get_status_summary(self) -> dict:
        """Résumé d'état pour dashboard."""
        return {
            "enabled": edge_decay_monitor_enabled(),
            "last_check": self.state.last_check_iso,
            "blacklisted_contexts": len(self.state.blacklisted_contexts),
            "demoted_principles": len(self.state.demoted_principles),
            "observation_mode": len(self.state.observation_mode),
            "recent_alerts": len([a for a in self.state.alerts_history 
                                 if time.time() - datetime.fromisoformat(a["timestamp"].replace("Z", "+00:00")).timestamp() < 3600]),
        }


# ──────────────────────────────────────────────────────────────────────────────
# API publique
# ──────────────────────────────────────────────────────────────────────────────

_monitor_instance: EdgeDecayMonitor | None = None


def get_edge_decay_monitor() -> EdgeDecayMonitor:
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = EdgeDecayMonitor()
    return _monitor_instance


def run_edge_decay_check(db_path: Path | str | None = None) -> list[Alert]:
    """Point d'entrée pour cron V9_EdgeDecayMonitor."""
    monitor = EdgeDecayMonitor(db_path)
    return monitor.check_all_principles()


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main() -> int:
    import argparse
    
    parser = argparse.ArgumentParser(description="Edge Decay Monitor V9")
    parser.add_argument("--principle", type=str, help="Check specific principle")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    
    monitor = get_edge_decay_monitor()
    
    if args.principle:
        alerts = monitor._check_principle(args.principle)
    else:
        alerts = monitor.check_all_principles()
    
    if args.json:
        print(json.dumps([a.to_dict() for a in alerts], indent=2, ensure_ascii=False))
    else:
        if not alerts:
            print("✅ Aucune alerte de dégradation d'edge")
        else:
            for alert in alerts:
                icon = "🔴" if alert.level == "CRITICAL" else "🟡"
                print(f"{icon} [{alert.level}] {alert.principle_id} | {alert.session} | {alert.regime_type}")
                print(f"    {alert.message}")
                print(f"    Action: {alert.action}")
                print()
    
    return 0 if not alerts else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())