"""portfolio_risk_manager.py — Risk management au niveau portfolio.

Un stratège institutionnel ne gère pas le risque par trade isolé — il gère
le risque au niveau portfolio. Ce module :

1. Calcule l'exposition nette par devise (long USD vs short USD global)
2. Détecte les corrélations entre paires ouvertes
3. Limite le risque total (portfolio heat)
4. Circuit breaker après N pertes consécutives
5. Max drawdown rolling (stop si drawdown > X% sur 24h)

Usage :
    from core.v9.portfolio_risk_manager import PortfolioRiskManager
    prm = PortfolioRiskManager(db_path="data/v9_forces.db")
    go, reason = prm.evaluate_portfolio(open_trades, new_trade)
    if not go:
        # Refuser le trade
        ...

Doctrine :
  - R18 : code pur, stdlib uniquement
  - R2 : additif — ne remplace pas PaperRiskManager, s'ajoute avant
  - R6 : try/except, jamais bloquant
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.v9.config import DB_PATH
from core.v9.db_schema import get_connection

log = logging.getLogger(__name__)

PORTFOLIO_RISK_VERSION = "1.0"

# ── Paramètres institutionnels ──────────────────────────────────────

# Exposition nette max par devise (en nombre de lots directionnels)
# 3 = on peut avoir au max 3 trades short USD simultanés
MAX_NET_EXPOSURE_PER_CURRENCY = 3

# Risque total max du portfolio (en % du capital)
MAX_PORTFOLIO_HEAT_PCT = 6.0

# Nombre max de pertes consécutives avant circuit breaker
MAX_CONSECUTIVE_LOSSES = 5

# Pause après circuit breaker (en heures)
CIRCUIT_BREAKER_PAUSE_HOURS = 1.0

# Max drawdown sur 24h (en pips) avant halt
MAX_DRAWDOWN_24H_PIPS = 200.0

# Corrélation max entre deux paires ouvertes (au-dessus = réduction sizing)
CORRELATION_THRESHOLD = 0.7

# Réduction de sizing si corrélation élevée
CORRELATION_SIZING_REDUCTION = 0.5

# Paires corrélées (basé sur l'analyse empirique)
# GBPUSD ↔ EURUSD : 0.85 (partagent EUR et USD)
# USDCHF ↔ EURUSD : 0.75 (CHF et EUR corrélés)
# USDCAD ↔ GBPUSD : 0.3 (faible)
CORRELATION_MATRIX: dict[str, dict[str, float]] = {
    "GBPUSD": {"EURUSD": 0.85, "USDCHF": 0.5, "USDJPY": 0.3, "USDCAD": 0.3, "AUDUSD": 0.4},
    "EURUSD": {"GBPUSD": 0.85, "USDCHF": 0.75, "USDJPY": 0.4, "USDCAD": 0.3, "AUDUSD": 0.4},
    "USDCHF": {"GBPUSD": 0.5, "EURUSD": 0.75, "USDJPY": 0.3, "USDCAD": 0.3, "AUDUSD": 0.3},
    "USDJPY": {"GBPUSD": 0.3, "EURUSD": 0.4, "USDCHF": 0.3, "USDCAD": 0.2, "AUDUSD": 0.3},
    "USDCAD": {"GBPUSD": 0.3, "EURUSD": 0.3, "USDCHF": 0.3, "USDJPY": 0.2, "AUDUSD": 0.4},
    "AUDUSD": {"GBPUSD": 0.4, "EURUSD": 0.4, "USDCHF": 0.3, "USDJPY": 0.3, "USDCAD": 0.4},
}

# Devises de base par paire (pour le calcul d'exposition nette)
BASE_CURRENCY: dict[str, str] = {
    "GBPUSD": "USD",  # short GBPUSD = long USD
    "EURUSD": "USD",
    "USDJPY": "USD",
    "USDCAD": "USD",
    "USDCHF": "USD",
    "AUDUSD": "USD",
}


class PortfolioRiskManager:
    """Gère le risque au niveau portfolio, pas juste par trade.

    Vérifie avant chaque nouveau trade :
    1. Exposition nette par devise (pas trop de trades dans le même sens)
    2. Corrélation entre paires ouvertes (réduire le sizing si corrélé)
    3. Portfolio heat (risque total < X% du capital)
    4. Circuit breaker (pause après N pertes consécutives)
    5. Max drawdown 24h (stop si drawdown > seuil)
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH

    def _connect(self) -> sqlite3.Connection:
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def evaluate_portfolio(
        self,
        open_trades: list[dict[str, Any]],
        new_trade: dict[str, Any],
    ) -> tuple[bool, str | None, float]:
        """Évalue si un nouveau trade est acceptable au niveau portfolio.

        Args:
            open_trades: liste des trades ouverts (dict avec symbol, direction, risk_amount)
            new_trade: dict du nouveau trade (symbol, direction, risk_amount)

        Returns:
            (go, reason, sizing_multiplier)
            - go: True si le trade est accepté
            - reason: raison de refus si go=False
            - sizing_multiplier: 1.0 par défaut, réduit si corrélation élevée
        """
        try:
            # 1. Circuit breaker
            cb = self._check_circuit_breaker()
            if cb is not None:
                return False, cb, 0.0

            # 2. Max drawdown 24h
            dd = self._check_drawdown_24h()
            if dd is not None:
                return False, dd, 0.0

            # 3. Exposition nette par devise
            net = self._check_net_exposure(open_trades, new_trade)
            if net is not None:
                return False, net, 0.0

            # 4. Portfolio heat
            heat = self._check_portfolio_heat(open_trades, new_trade)
            if heat is not None:
                return False, heat, 0.0

            # 5. Corrélation → réduction sizing (pas de refus, juste réduction)
            sizing_mult = self._check_correlation(open_trades, new_trade)

            return True, None, sizing_mult
        except Exception as exc:
            log.debug("portfolio_risk: evaluate failed: %s", exc)
            return True, None, 1.0  # R6 : ne jamais bloquer en cas d'erreur

    def _check_circuit_breaker(self) -> str | None:
        """Vérifie si le circuit breaker est actif (N pertes consécutives)."""
        try:
            conn = self._connect()
            try:
                # Derniers trades clôturés
                rows = conn.execute(
                    "SELECT is_win, closed_at FROM paper_trades "
                    "WHERE closed_at IS NOT NULL "
                    "ORDER BY closed_at DESC LIMIT ?",
                    (MAX_CONSECUTIVE_LOSSES,),
                ).fetchall()

                if len(rows) < MAX_CONSECUTIVE_LOSSES:
                    return None

                # Toutes les N dernières sont des pertes ?
                all_losses = all(r["is_win"] == 0 for r in rows)
                if not all_losses:
                    return None

                # Vérifier si la pause est encore active
                last_loss_time = rows[0]["closed_at"]
                try:
                    last_dt = datetime.fromisoformat(
                        last_loss_time.replace("Z", "+00:00")
                    )
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=timezone.utc)
                    elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
                    if elapsed < CIRCUIT_BREAKER_PAUSE_HOURS:
                        return f"circuit_breaker ({MAX_CONSECUTIVE_LOSSES} pertes consécutives, pause {CIRCUIT_BREAKER_PAUSE_HOURS}h)"
                except Exception:
                    pass
                return None
            finally:
                conn.close()
        except Exception:
            return None

    def _check_drawdown_24h(self) -> str | None:
        """Vérifie si le drawdown sur 24h dépasse le seuil."""
        try:
            conn = self._connect()
            try:
                cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
                row = conn.execute(
                    "SELECT COALESCE(SUM(pips_simulated), 0) as total_pips "
                    "FROM paper_trades "
                    "WHERE closed_at IS NOT NULL AND closed_at > ?",
                    (cutoff,),
                ).fetchone()

                if row and row["total_pips"] < -MAX_DRAWDOWN_24H_PIPS:
                    return f"max_drawdown_24h ({row['total_pips']:.1f} pips < -{MAX_DRAWDOWN_24H_PIPS})"
                return None
            finally:
                conn.close()
        except Exception:
            return None

    def _check_net_exposure(
        self,
        open_trades: list[dict[str, Any]],
        new_trade: dict[str, Any],
    ) -> str | None:
        """Vérifie l'exposition nette par devise."""
        new_symbol = new_trade.get("symbol", "")
        new_direction = new_trade.get("direction", "")
        base_currency = BASE_CURRENCY.get(new_symbol, "USD")

        # Compter l'exposition existante sur cette devise
        net_exposure = 0
        for t in open_trades:
            t_symbol = t.get("symbol", "")
            t_direction = t.get("direction", "")
            if BASE_CURRENCY.get(t_symbol, "USD") == base_currency:
                # short = +1 USD exposure, long = -1
                if t_direction == "baissiere":
                    net_exposure += 1
                elif t_direction == "haussiere":
                    net_exposure -= 1

        # Ajouter le nouveau trade
        if new_direction == "baissiere":
            net_exposure += 1
        elif new_direction == "haussiere":
            net_exposure -= 1

        if abs(net_exposure) > MAX_NET_EXPOSURE_PER_CURRENCY:
            return f"net_exposure_{base_currency} ({net_exposure} > {MAX_NET_EXPOSURE_PER_CURRENCY})"

        return None

    def _check_portfolio_heat(
        self,
        open_trades: list[dict[str, Any]],
        new_trade: dict[str, Any],
    ) -> str | None:
        """Vérifie que le risque total du portfolio ne dépasse pas le seuil."""
        try:
            total_risk = sum(
                float(t.get("risk_amount", 0) or 0) for t in open_trades
            )
            new_risk = float(new_trade.get("risk_amount", 0) or 0)
            total_risk += new_risk

            # Capital (lu depuis paper_risk_manager ou défaut 10000)
            capital = float(new_trade.get("capital", 10000) or 10000)
            heat_pct = (total_risk / capital * 100) if capital > 0 else 0

            if heat_pct > MAX_PORTFOLIO_HEAT_PCT:
                return f"portfolio_heat ({heat_pct:.1f}% > {MAX_PORTFOLIO_HEAT_PCT}%)"

            return None
        except Exception:
            return None

    def _check_correlation(
        self,
        open_trades: list[dict[str, Any]],
        new_trade: dict[str, Any],
    ) -> float:
        """Calcule le sizing multiplier basé sur la corrélation.

        Si le nouveau trade est fortement corrélé avec un trade ouvert,
        on réduit le sizing pour éviter une double exposition.
        """
        new_symbol = new_trade.get("symbol", "")
        new_direction = new_trade.get("direction", "")

        max_corr = 0.0
        for t in open_trades:
            t_symbol = t.get("symbol", "")
            t_direction = t.get("direction", "")

            # Corrélation entre les deux paires
            corr = CORRELATION_MATRIX.get(new_symbol, {}).get(t_symbol, 0.0)

            # Si même direction → la corrélation augmente le risque
            # Si direction opposée → la corrélation diminue le risque (hedge)
            if t_direction == new_direction:
                max_corr = max(max_corr, corr)

        if max_corr > CORRELATION_THRESHOLD:
            return CORRELATION_SIZING_REDUCTION
        elif max_corr > 0.5:
            return 0.7  # réduction modérée
        return 1.0

    def get_portfolio_stats(self) -> dict[str, Any]:
        """Retourne les statistiques actuelles du portfolio."""
        try:
            conn = self._connect()
            try:
                # Trades ouverts
                open_count = conn.execute(
                    "SELECT COUNT(*) FROM paper_trades WHERE closed_at IS NULL"
                ).fetchone()[0]

                # WR global
                row = conn.execute(
                    "SELECT COUNT(*) as n, COALESCE(SUM(is_win), 0) as wins, "
                    "COALESCE(SUM(pips_simulated), 0) as total_pips "
                    "FROM paper_trades WHERE closed_at IS NOT NULL"
                ).fetchone()

                # Drawdown 24h
                cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
                dd_row = conn.execute(
                    "SELECT COALESCE(SUM(pips_simulated), 0) as pips "
                    "FROM paper_trades "
                    "WHERE closed_at IS NOT NULL AND closed_at > ?",
                    (cutoff,),
                ).fetchone()

                # Pertes consécutives
                losses = conn.execute(
                    "SELECT is_win FROM paper_trades "
                    "WHERE closed_at IS NOT NULL "
                    "ORDER BY closed_at DESC LIMIT 10"
                ).fetchall()
                consecutive = 0
                for l in losses:
                    if l["is_win"] == 0:
                        consecutive += 1
                    else:
                        break

                return {
                    "open_trades": open_count,
                    "total_closed": row["n"],
                    "wins": row["wins"],
                    "wr": round(row["wins"] / row["n"] * 100, 1) if row["n"] > 0 else 0,
                    "total_pips": round(row["total_pips"], 2),
                    "pips_24h": round(dd_row["pips"], 2),
                    "consecutive_losses": consecutive,
                    "circuit_breaker_active": consecutive >= MAX_CONSECUTIVE_LOSSES,
                    "version": PORTFOLIO_RISK_VERSION,
                }
            finally:
                conn.close()
        except Exception as exc:
            log.debug("portfolio_risk: stats failed: %s", exc)
            return {"error": str(exc)}