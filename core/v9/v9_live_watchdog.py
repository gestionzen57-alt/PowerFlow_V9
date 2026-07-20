"""v9_live_watchdog.py — Watchdog live edgefund (Axe 6, audit edgefund 2026-07-19).

**Pourquoi ce module existe**
La réouverture live (dim 22h UTC) réactive le paper-trading après le désastre du
17/07. L'audit edgefund (Axe 1) a montré que le désastre était une **boucle** (85 %,
déjà traitée par `v9_loop_breaker`) + un **régime baissier défavorable** (mitigé par
long-only). Le watchdog est la 3e ligne de défense : il **surveille l'edge live en
continu** et **recommande** l'arrêt si le live diverge du backtest.

**Ce que fait le module**
- Lecture seule STRICTE sur `v9_forces.db` (URI `mode=ro`), table `paper_trades`.
- Segmente le win-rate sur le **scénario réel de la motion** :
  `symbol='GBPUSD' AND direction='haussiere'` (long-only). Les autres paires /
  directions sont ignorées pour le verdict (elles sont déjà bloquées par
  `V9_NO_BAISSIERE` / `V9_GBPUSD_LONG_ONLY`).
- Calcule : P&L net 24h (pips nets, toutes paires), win-rate GBPUSD long-only.
- Retourne une `WatchdogDecision` avec statut + actions **recommandées** + niveau d'alerte.
- **Ne modifie JAMAIS** les kill switches ni `config.py` (R30). Il *recommande* ; un
  opérateur / cron applique. Défense-in-depth, pas d'auto-mutation destructive.

**Correctifs 2026-07-19 (pré-réouverture)**
1. Action P0 = `V9_PAPER_TRADE_HALT=1` (+ `V9_NO_BAISSIERE=1`) ; le watchdog ne
   désactive JAMAIS le long-only (le désactiver ré-autoriserait les shorts au
   lieu d'arrêter).
2. Connexion SQLite read-only stricte (`file:...?mode=ro`).
3. Win-rate segmenté par (symbol, direction) = GBPUSD haussiere.
4. `dd_24h_pips` renommé `net_pnl_24h_pips` (c'était un P&L net, pas un drawdown).
5. `db_error` distinct de `no_data` : télémétrie muette = danger → alerte p0.

**Seuils (playbook Axe 6)**
| Déclencheur | Seuil défaut | Action recommandée |
|---|---|---|
| P&L net 24h | < −200 pips | V9_TRADER_MINI_ENABLED=0 (warn) |
| WR GBPUSD long (50 trades) | < 80 % | V9_TRADER_MINI_ENABLED=0 (warn) |
| WR GBPUSD long (50 trades) | < 60 % | V9_PAPER_TRADE_HALT=1 → arrêt total (P0) |

**Volet doctrinal** : R2 additif, R6 défensif (try/except → jamais de crash),
R7 testable (lecture seule DB), R18 code pur (sqlite3 + math), R22 1 périmètre.

**Activation** : kill switch `V9_LIVE_WATCHDOG_ENABLED` (défaut OFF tant que motion CEO).
Si OFF → `check_health` retourne statut "disabled" (aucune recommandation).
"""
from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ const / env

LIVE_WATCHDOG_ENABLED_ENV = "V9_LIVE_WATCHDOG_ENABLED"
DD_24H_PIPS_ENV = "V9_WATCHDOG_DD_24H_PIPS"      # seuil P&L net 24h (nom env historique)
WR_WINDOW_ENV = "V9_WATCHDOG_WR_WINDOW"
WR_WARN_ENV = "V9_WATCHDOG_WR_WARN"
WR_CRIT_ENV = "V9_WATCHDOG_WR_CRIT"
NEUTRE_RATE_WARN_ENV = "V9_WATCHDOG_NEUTRE_RATE_WARN"  # motion CEO #8 §5.3

DEFAULT_DD_24H_PIPS = -200.0     # P&L net 24h toléré (pips nets)
DEFAULT_WR_WINDOW = 50           # nb de trades récents pour le WR
DEFAULT_WR_WARN = 0.80           # WR < 80 % → warn (couper trader mini)
DEFAULT_WR_CRIT = 0.60           # WR < 60 % → critique (arrêt total)
DEFAULT_NEUTRE_RATE_WARN = 75.0  # % regime NEUTRE 24h (Opus §5.3 : biais 82% actuel)
MIN_TRADES_FOR_WR = 10           # en-dessous : pas assez d'historique → no_data

# Scénario surveillé (motion long-only). Le watchdog ne juge que ce segment.
WATCHDOG_SYMBOL = "GBPUSD"
WATCHDOG_DIRECTION = "haussiere"

# Actions recommandées — VRAI arrêt (ne désactive jamais le long-only, cf. audit 07-19).
ACTION_HALT = "V9_PAPER_TRADE_HALT=1"
ACTION_NO_BAISSIERE = "V9_NO_BAISSIERE=1"
ACTION_TRADER_MINI_OFF = "V9_TRADER_MINI_ENABLED=0"


class WatchdogDBError(Exception):
    """Erreur de lecture DB (absente, schema incompatible, verrouillée...).

    Distincte d'un simple « aucune ligne » : une DB muette est un danger
    (télémétrie perdue) → le watchdog remonte une alerte p0.
    """


@dataclass(frozen=True)
class WatchdogDecision:
    """Verdict du watchdog sur la santé live."""
    status: str                                  # "ok"|"warn"|"critical"|"disabled"|"no_data"|"db_error"
    net_pnl_24h_pips: float                       # P&L net 24h (toutes paires), pips
    wr_long_only_gbpusd: float                    # WR segmenté GBPUSD haussiere
    n_recent: int                                 # nb trades GBPUSD long dans la fenêtre
    triggered: tuple[str, ...] = ()
    recommended_actions: tuple[str, ...] = ()
    alert_level: str = "none"                    # "none" | "warn" | "p0"
    neutre_rate_24h_pct: float = 0.0             # motion CEO #8 §5.3 — % regime NEUTRE 24h

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "net_pnl_24h_pips": self.net_pnl_24h_pips,
            "wr_long_only_gbpusd": self.wr_long_only_gbpusd,
            "n_recent": self.n_recent,
            "triggered": list(self.triggered),
            "recommended_actions": list(self.recommended_actions),
            "alert_level": self.alert_level,
            "neutre_rate_24h_pct": self.neutre_rate_24h_pct,
        }


# ------------------------------------------------------------------ kill switch helpers


def live_watchdog_enabled() -> bool:
    """Kill switch V9_LIVE_WATCHDOG_ENABLED.

    Source de vérité = `core.v9.kill_switches` (lit le `.env`, priorité
    env > fichier). Fallback `os.environ` seulement si l'import échoue.
    """
    try:
        from core.v9.kill_switches import live_watchdog_enabled as _ks
        return _ks()
    except Exception:
        return os.environ.get(LIVE_WATCHDOG_ENABLED_ENV, "0") in ("1", "true", "True")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------------ DB (lecture seule STRICTE)


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    """Ouvre une connexion SQLite **read-only stricte** (`mode=ro`).

    Lève `WatchdogDBError` si la DB est absente ou impossible à ouvrir.
    """
    if not db_path.exists():
        raise WatchdogDBError(f"db not found: {db_path}")
    try:
        # URI read-only : toute tentative d'écriture lève OperationalError.
        return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5.0)
    except sqlite3.OperationalError as e:
        raise WatchdogDBError(f"connect failed: {e}") from e


def _fetch_recent_long_only(
    db_path: Path, window: int,
) -> list[tuple[str | None, float, int]]:
    """Retourne les `window` derniers trades CLÔTURÉS **GBPUSD haussiere**.

    `paper_trades` n'a pas de colonne symbol → jointure `decisions` via
    `snapshot_id`. `direction` est lue sur `paper_trades` (direction réelle
    du trade). Lecture seule stricte. Ordonné du plus récent au plus ancien.

    Lève `WatchdogDBError` sur toute erreur DB (schema, verrou, corruption).
    Un résultat vide ([]) n'est PAS une erreur (= pas de trade du segment).
    """
    conn = _connect_ro(db_path)
    try:
        rows = conn.execute(
            """
            SELECT pt.closed_at, pt.pips_simulated, pt.is_win
            FROM paper_trades pt
            JOIN decisions d ON d.snapshot_id = pt.snapshot_id
            WHERE pt.closed_at IS NOT NULL
              AND pt.pips_simulated IS NOT NULL
              AND d.symbol = ?
              AND pt.direction = ?
            ORDER BY pt.closed_at DESC
            LIMIT ?
            """,
            (WATCHDOG_SYMBOL, WATCHDOG_DIRECTION, max(1, window)),
        ).fetchall()
        return [(r[0], float(r[1]), int(r[2] or 0)) for r in rows]
    except sqlite3.OperationalError as e:
        raise WatchdogDBError(f"query recent failed: {e}") from e
    finally:
        conn.close()


def _fetch_neutre_rate_24h(db_path: Path) -> float:
    """Taux de régime NEUTRE sur les 24h (motion CEO #8 §5.3 — Opus audit).

    Lit `core.v9.v9_cross_pair_metrics.neutre_rate_24h()`. R6 : retourne 0.0
    sur toute erreur (DB absente, table manquante, dépendance HS). Le
    watchdog ne lève JAMAIS à l'appelant.

    Seuil par défaut 75 % (configurable via V9_WATCHDOG_NEUTRE_RATE_WARN).
    Au-delà, le détecteur est suspecté d'être saturé par des ticks stables
    qui masquent des retournements — c'est exactement le pattern 24h baissier
    vécu (74/104 trades baissiers classés NEUTRE).
    """
    try:
        from core.v9.v9_cross_pair_metrics import neutre_rate_24h
        res = neutre_rate_24h(db_path=db_path)
        return float(res.get("pct", 0.0))
    except Exception as e:  # noqa: BLE001
        logger.debug("watchdog: neutre_rate fetch KO : %s", e)
        return 0.0


def _fetch_net_pnl_24h(db_path: Path) -> float:
    """P&L net 24h = pips nets cumulés sur les trades clôturés depuis 24h.

    Toutes paires / directions (métrique de santé globale, volontairement
    simple). Lecture seule stricte. Lève `WatchdogDBError` sur erreur DB.
    """
    conn = _connect_ro(db_path)
    try:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(pips_simulated), 0.0)
            FROM paper_trades
            WHERE closed_at IS NOT NULL
              AND pips_simulated IS NOT NULL
              AND closed_at > datetime('now', '-24 hours')
            """
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0
    except sqlite3.OperationalError as e:
        raise WatchdogDBError(f"query pnl failed: {e}") from e
    finally:
        conn.close()


# ------------------------------------------------------------------ API publique


def _db_error_decision(reason: str) -> WatchdogDecision:
    """Verdict fail-safe quand la télémétrie est muette (R6) : alerte p0."""
    return WatchdogDecision(
        status="db_error",
        net_pnl_24h_pips=0.0,
        wr_long_only_gbpusd=0.0,
        n_recent=0,
        triggered=(f"db_error: {reason}",),
        recommended_actions=(ACTION_HALT, ACTION_NO_BAISSIERE),
        alert_level="p0",
    )


def check_health(db_path: Path | str | None = None) -> WatchdogDecision:
    """Évalue la santé live et recommande des actions.

    - Si `V9_LIVE_WATCHDOG_ENABLED=0` (défaut) → statut "disabled", aucune reco (R6).
    - Si la DB est muette (absente/schema/verrou) → "db_error" + alerte p0.
    - Si moins de `MIN_TRADES_FOR_WR` trades GBPUSD long → "no_data" (pas d'alerte).

    Returns:
        WatchdogDecision (statut, P&L net 24h, WR long-only, actions, alerte).
    """
    if not live_watchdog_enabled():
        return WatchdogDecision(
            status="disabled", net_pnl_24h_pips=0.0,
            wr_long_only_gbpusd=0.0, n_recent=0,
        )

    if db_path is None:
        db_path = Path("data/v9_forces.db")
    db_p = Path(db_path) if not isinstance(db_path, Path) else db_path

    dd_limit = _env_float(DD_24H_PIPS_ENV, DEFAULT_DD_24H_PIPS)
    window = _env_int(WR_WINDOW_ENV, DEFAULT_WR_WINDOW)
    wr_warn = _env_float(WR_WARN_ENV, DEFAULT_WR_WARN)
    wr_crit = _env_float(WR_CRIT_ENV, DEFAULT_WR_CRIT)
    neutre_warn = _env_float(NEUTRE_RATE_WARN_ENV, DEFAULT_NEUTRE_RATE_WARN)

    try:
        trades = _fetch_recent_long_only(db_p, window)
        net_pnl = _fetch_net_pnl_24h(db_p)
        neutre_rate = _fetch_neutre_rate_24h(db_p)
    except WatchdogDBError as e:
        logger.warning("watchdog: db_error: %s", e)
        return _db_error_decision(str(e))
    except Exception as e:  # R6 : jamais de crash, télémétrie muette = danger
        logger.warning("watchdog: unexpected db failure: %s", e)
        return _db_error_decision(f"unexpected: {e}")

    n_recent = len(trades)

    # Segment insuffisant → pas de verdict WR (pas d'alerte).
    if n_recent < MIN_TRADES_FOR_WR:
        return WatchdogDecision(
            status="no_data",
            net_pnl_24h_pips=round(net_pnl, 1),
            wr_long_only_gbpusd=0.0,
            n_recent=n_recent,
            neutre_rate_24h_pct=round(neutre_rate, 2),
        )

    wr = sum(t[2] for t in trades) / n_recent

    triggered: list[str] = []
    actions: list[str] = []
    alert = "none"
    status = "ok"

    # Seuil critique WR (arrêt total) — priorité maximale.
    if wr < wr_crit:
        triggered.append(
            f"wr_critical: {wr*100:.1f}% < {wr_crit*100:.0f}% sur "
            f"{n_recent} trades GBPUSD long"
        )
        # VRAI arrêt : halt total + renforcement no-baissière. JAMAIS long_only=0.
        actions.append(ACTION_HALT)
        actions.append(ACTION_NO_BAISSIERE)
        alert = "p0"
        status = "critical"
    # Seuil warn WR (couper trader mini).
    elif wr < wr_warn:
        triggered.append(
            f"wr_warn: {wr*100:.1f}% < {wr_warn*100:.0f}% sur "
            f"{n_recent} trades GBPUSD long"
        )
        actions.append(ACTION_TRADER_MINI_OFF)
        alert = "warn"
        status = "warn"

    # Seuil P&L net 24h (indépendant du WR).
    if net_pnl < dd_limit:
        triggered.append(f"net_pnl_24h: {net_pnl:.1f} pips < {dd_limit:.0f} pips")
        if status == "critical":
            # Le halt total couvre déjà ce cas — pas de reco additionnelle.
            pass
        else:
            if ACTION_TRADER_MINI_OFF not in actions:
                actions.append(ACTION_TRADER_MINI_OFF)
            if alert == "none":
                alert = "warn"
            if status == "ok":
                status = "warn"

    # Motion CEO #8 §5.3 — NEUTRE_RATE_24H > 75 % indique un détecteur saturé
    # (biais de calibration documenté par Opus : 82 % actuel). Ne déclenche
    # PAS d'action (le détecteur est peut-être correct) — alerte WARN
    # d'investigation uniquement. R2 additif, R6 défensif.
    if neutre_rate > neutre_warn:
        triggered.append(
            f"neutre_rate_24h: {neutre_rate:.1f}% > {neutre_warn:.0f}% "
            f"(détecteur suspecté saturé — calibrer SEUIL_PALIER)"
        )
        if alert == "none":
            alert = "warn"
        if status == "ok":
            status = "warn"

    return WatchdogDecision(
        status=status,
        net_pnl_24h_pips=round(net_pnl, 1),
        wr_long_only_gbpusd=round(wr, 4),
        n_recent=n_recent,
        triggered=tuple(triggered),
        recommended_actions=tuple(actions),
        alert_level=alert,
        neutre_rate_24h_pct=round(neutre_rate, 2),
    )


def get_stats(db_path: Path | str | None = None) -> dict[str, Any]:
    """Stats de config du watchdog (diagnostic, sans verdict)."""
    return {
        "enabled": live_watchdog_enabled(),
        "dd_24h_limit_pips": _env_float(DD_24H_PIPS_ENV, DEFAULT_DD_24H_PIPS),
        "wr_window": _env_int(WR_WINDOW_ENV, DEFAULT_WR_WINDOW),
        "wr_warn": _env_float(WR_WARN_ENV, DEFAULT_WR_WARN),
        "wr_crit": _env_float(WR_CRIT_ENV, DEFAULT_WR_CRIT),
        "segment": f"{WATCHDOG_SYMBOL}/{WATCHDOG_DIRECTION}",
    }
