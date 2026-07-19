"""v9_live_watchdog.py — Watchdog live edgefund (Axe 6, audit edgefund 2026-07-19).

**Pourquoi ce module existe**
La réouverture live (dim 22h UTC) réactive le paper-trading après le désastre du
17/07. L'audit edgefund (Axe 1) a montré que le désastre était une **boucle** (85 %,
déjà traitée par `v9_loop_breaker`) + un **régime baissier défavorable** (mitigé par
long-only). Le watchdog est la 3e ligne de défense : il **surveille l'edge live en
continu** et **recommande** l'arrêt si le live diverge du backtest.

**Ce que fait le module**
- Lecture seule sur `v9_forces.db` (table `paper_trades`).
- Calcule : drawdown 24h (pips nets), win-rate sur la fenêtre récente.
- Retourne une `WatchdogDecision` avec statut + actions **recommandées** + niveau d'alerte.
- **Ne modifie JAMAIS** les kill switches ni `config.py` (R30). Il *recommande* ; un
  opérateur / cron applique. Défense-in-depth, pas d'auto-mutation destructive.

**Seuils (playbook Axe 6)**
| Déclencheur | Seuil défaut | Action recommandée |
|---|---|---|
| DD 24h | < −200 pips | V9_TRADER_MINI_ENABLED=0 (warn) |
| WR (50 trades) | < 80 % | V9_TRADER_MINI_ENABLED=0 (warn) |
| WR (50 trades) | < 60 % | V9_GBPUSD_LONG_ONLY=0 → arrêt total (P0) |

**Volet doctrinal** : R2 additif, R6 défensif (try/except → statut ok par défaut),
R7 testable (lecture seule DB), R18 code pur (sqlite3 + math), R22 1 périmètre.

**Activation** : kill switch `V9_LIVE_WATCHDOG_ENABLED` (défaut OFF tant que motion CEO).
Si OFF → `check_health` retourne statut "disabled" (aucune recommandation).
"""
from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ const / env

LIVE_WATCHDOG_ENABLED_ENV = "V9_LIVE_WATCHDOG_ENABLED"
DD_24H_PIPS_ENV = "V9_WATCHDOG_DD_24H_PIPS"
WR_WINDOW_ENV = "V9_WATCHDOG_WR_WINDOW"
WR_WARN_ENV = "V9_WATCHDOG_WR_WARN"
WR_CRIT_ENV = "V9_WATCHDOG_WR_CRIT"

DEFAULT_DD_24H_PIPS = -200.0     # drawdown 24h toléré (pips nets)
DEFAULT_WR_WINDOW = 50           # nb de trades récents pour le WR
DEFAULT_WR_WARN = 0.80           # WR < 80 % → warn (couper trader mini)
DEFAULT_WR_CRIT = 0.60           # WR < 60 % → critique (arrêt total)
MIN_TRADES_FOR_WR = 10           # en-dessous : pas assez d'historique, pas de verdict WR


@dataclass(frozen=True)
class WatchdogDecision:
    """Verdict du watchdog sur la santé live."""
    status: str                                  # "ok" | "warn" | "critical" | "disabled" | "no_data"
    dd_24h_pips: float
    wr_recent: float
    n_recent: int
    triggered: tuple[str, ...] = ()
    recommended_actions: tuple[str, ...] = ()
    alert_level: str = "none"                    # "none" | "warn" | "p0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "dd_24h_pips": self.dd_24h_pips,
            "wr_recent": self.wr_recent,
            "n_recent": self.n_recent,
            "triggered": list(self.triggered),
            "recommended_actions": list(self.recommended_actions),
            "alert_level": self.alert_level,
        }


# ------------------------------------------------------------------ kill switch helpers


def live_watchdog_enabled() -> bool:
    """Kill switch V9_LIVE_WATCHDOG_ENABLED (défaut OFF tant que pas motion CEO)."""
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


# ------------------------------------------------------------------ DB (lecture seule)


def _fetch_recent_trades(
    db_path: Path, window: int,
) -> list[tuple[str | None, float, int]]:
    """Retourne les `window` derniers trades CLÔTURÉS : (closed_at, pips, is_win).

    Lecture seule sur `paper_trades`. Ordonné du plus récent au plus ancien.
    """
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute(
                """
                SELECT closed_at, pips_simulated, is_win
                FROM paper_trades
                WHERE closed_at IS NOT NULL AND pips_simulated IS NOT NULL
                ORDER BY closed_at DESC
                LIMIT ?
                """,
                (max(1, window),),
            ).fetchall()
            return [(r[0], float(r[1]), int(r[2] or 0)) for r in rows]
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return []
    except Exception as e:  # R6 défensif
        logger.warning("watchdog: fetch_recent failed: %s", e)
        return []


def _fetch_dd_24h(db_path: Path) -> float:
    """Drawdown 24h = pips nets cumulés sur les trades clôturés depuis 24h.

    Métrique volontairement simple et robuste (net 24h). Un DD très négatif =
    perte soutenue → signal d'arrêt. Lecture seule.
    """
    if not db_path.exists():
        return 0.0
    try:
        conn = sqlite3.connect(str(db_path))
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
        except sqlite3.OperationalError:
            return 0.0
        finally:
            conn.close()
    except Exception as e:  # R6 défensif
        logger.warning("watchdog: fetch_dd failed: %s", e)
        return 0.0


# ------------------------------------------------------------------ API publique


def check_health(db_path: Path | str | None = None) -> WatchdogDecision:
    """Évalue la santé live et recommande des actions.

    Si `V9_LIVE_WATCHDOG_ENABLED=0` (défaut) → statut "disabled", aucune reco (R6).

    Returns:
        WatchdogDecision (statut, dd_24h, wr, actions recommandées, niveau d'alerte).
    """
    if not live_watchdog_enabled():
        return WatchdogDecision(
            status="disabled", dd_24h_pips=0.0, wr_recent=0.0, n_recent=0,
        )

    if db_path is None:
        db_path = Path("data/v9_forces.db")
    db_p = Path(db_path) if not isinstance(db_path, Path) else db_path

    dd_limit = _env_float(DD_24H_PIPS_ENV, DEFAULT_DD_24H_PIPS)
    window = _env_int(WR_WINDOW_ENV, DEFAULT_WR_WINDOW)
    wr_warn = _env_float(WR_WARN_ENV, DEFAULT_WR_WARN)
    wr_crit = _env_float(WR_CRIT_ENV, DEFAULT_WR_CRIT)

    trades = _fetch_recent_trades(db_p, window)
    dd_24h = _fetch_dd_24h(db_p)
    n_recent = len(trades)

    if n_recent == 0:
        return WatchdogDecision(
            status="no_data", dd_24h_pips=dd_24h, wr_recent=0.0, n_recent=0,
        )

    wr = sum(t[2] for t in trades) / n_recent

    triggered: list[str] = []
    actions: list[str] = []
    alert = "none"
    status = "ok"

    # Seuil critique WR (arrêt total) — priorité maximale.
    if n_recent >= MIN_TRADES_FOR_WR and wr < wr_crit:
        triggered.append(
            f"wr_critical: {wr*100:.1f}% < {wr_crit*100:.0f}% sur {n_recent} trades"
        )
        actions.append("V9_GBPUSD_LONG_ONLY=0")   # arrêt total
        actions.append("V9_TRADER_MINI_ENABLED=0")
        alert = "p0"
        status = "critical"
    # Seuil warn WR (couper trader mini).
    elif n_recent >= MIN_TRADES_FOR_WR and wr < wr_warn:
        triggered.append(
            f"wr_warn: {wr*100:.1f}% < {wr_warn*100:.0f}% sur {n_recent} trades"
        )
        actions.append("V9_TRADER_MINI_ENABLED=0")
        alert = "warn"
        status = "warn"

    # Seuil drawdown 24h (indépendant du WR).
    if dd_24h < dd_limit:
        triggered.append(f"dd_24h: {dd_24h:.1f} pips < {dd_limit:.0f} pips")
        if "V9_TRADER_MINI_ENABLED=0" not in actions:
            actions.append("V9_TRADER_MINI_ENABLED=0")
        if alert == "none":
            alert = "warn"
        if status == "ok":
            status = "warn"

    return WatchdogDecision(
        status=status,
        dd_24h_pips=round(dd_24h, 1),
        wr_recent=round(wr, 4),
        n_recent=n_recent,
        triggered=tuple(triggered),
        recommended_actions=tuple(actions),
        alert_level=alert,
    )


def get_stats(db_path: Path | str | None = None) -> dict[str, Any]:
    """Stats de config du watchdog (diagnostic, sans verdict)."""
    return {
        "enabled": live_watchdog_enabled(),
        "dd_24h_limit_pips": _env_float(DD_24H_PIPS_ENV, DEFAULT_DD_24H_PIPS),
        "wr_window": _env_int(WR_WINDOW_ENV, DEFAULT_WR_WINDOW),
        "wr_warn": _env_float(WR_WARN_ENV, DEFAULT_WR_WARN),
        "wr_crit": _env_float(WR_CRIT_ENV, DEFAULT_WR_CRIT),
    }
