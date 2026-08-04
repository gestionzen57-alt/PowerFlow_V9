"""
Phase 179 (03/08) : v9_signal_alerter — alertes Telegram temps réel entrées de position.

R2 additif pur : aucun fichier core/ modifié. Le script :
  - Poll la DB v9_forces.db toutes les POLL_SEC secondes
  - Détecte les nouveaux signaux "vraie entrée" :
      direction IN ('haussiere', 'baissiere')
      AND confiance >= RISK_CONFIANCE_MIN (= 70, aligné RiskManager)
      AND exploitability_statut = 'exploitable'
  - Envoie une alerte Telegram (canal CEO Søn) via send_telegram() du
    module canonique scripts/v9_telegram_notifier.py
  - R6 fail-open : sans token Telegram → log console + accumule dans
    un buffer in-memory, n'interrompt jamais la boucle
  - R18 : pas de LLM, templates de messages statiques

Critère "vraie entrée" aligné avec la doctrine V9 :
  - Phase 9 : décision = signal directionnel + exploitable + confiance
    suffisante (RiskManager.CONFIANCE_MIN = 70)
  - Pas de colonne `action` dans la table `signals` (decision_logger
    persiste la décision dans `contexte_complet_json` zlib-compressé
    → pas requêtable en SQL direct). Le critère est donc reconstruit
    à partir des champs requêtables : direction + confiance +
    exploitability_statut. C'est le filtre canonique côté lecture DB.

Usage :
  # PowerShell (set env d'abord)
  $env:V9_TELEGRAM_BOT_TOKEN = "..."   # optionnel
  $env:V9_TELEGRAM_CHAT_ID   = "..."   # optionnel
  .venv\Scripts\python.exe scripts\v9_signal_alerter.py

  # Sans Telegram : log console uniquement (R6 fail-open)
  .venv\Scripts\python.exe scripts/v9_signal_alerter.py
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Config ─────────────────────────────────────────────────────────────
# ROOT_DIR : parent de scripts/. Résolu depuis l'emplacement du fichier.
ROOT_DIR = Path(__file__).resolve().parent.parent

# DB path (aligné core/v9/config.DB_PATH)
DB_PATH = ROOT_DIR / "data" / "v9_forces.db"
if not DB_PATH.exists():
    # Fallback : cherche le plus gros .db dans data/
    candidates = sorted(
        (ROOT_DIR / "data").rglob("*.db"),
        key=lambda p: p.stat().st_size,
        reverse=True,
    )
    if candidates:
        DB_PATH = candidates[0]

# Telegram : env var prioritaire, fallback config/telegram.json
TELEGRAM_BOT_TOKEN = os.environ.get("V9_TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("V9_TELEGRAM_CHAT_ID", "").strip()
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    try:
        tg_cfg_path = ROOT_DIR / "config" / "telegram.json"
        if tg_cfg_path.exists():
            cfg = json.loads(tg_cfg_path.read_text(encoding="utf-8"))
            TELEGRAM_BOT_TOKEN = TELEGRAM_BOT_TOKEN or str(cfg.get("BOT_TOKEN", "")).strip()
            TELEGRAM_CHAT_ID = TELEGRAM_CHAT_ID or str(cfg.get("CHAT_ID", "")).strip()
    except Exception:
        pass

# RiskManager.CONFIANCE_MIN aligné (voir core/v9/risk_manager.py si besoin)
RISK_CONFIANCE_MIN = 70
POLL_SEC = 5
LOOKBACK_SEC = 60  # fenêtre glissante (60s = 12 polls de marge)

# Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] v9_signal_alerter: %(message)s",
)
log = logging.getLogger("v9.signal_alerter")

# Emoji direction (CP1252-safe pour console Windows)
EMOJI = {
    "haussiere": "🟢",  # vert
    "baissiere": "🔴",  # rouge
}

# Buffer in-memory (R6 fail-open si pas de Telegram)
_console_buffer: deque[str] = deque(maxlen=100)


# ── Dataclass alerte ───────────────────────────────────────────────────
@dataclass
class SignalAlert:
    signal_id: str
    symbol: str
    timeframe: str
    direction: str
    confiance: int
    confiance_calibree: int | None
    exploitability_statut: str
    regime_type: str | None
    predictor_action: str | None
    predictor_edge_pips: float | None
    timestamp: str
    principles: list[str] = field(default_factory=list)

    def format_telegram(self) -> str:
        emoji = EMOJI.get(self.direction, "⚡")
        # HTML parse_mode (aligné decision_logger style)
        principles_str = ", ".join(self.principles[:5]) if self.principles else "n/a"
        if len(self.principles) > 5:
            principles_str += f" (+{len(self.principles) - 5})"
        return (
            f"{emoji} <b>SIGNAL V9 ENTREE</b> {emoji}\n"
            f"\n"
            f"<b>Paire</b>    : {self.symbol} {self.timeframe}\n"
            f"<b>Direction</b>: <b>{self.direction.upper()}</b>\n"
            f"<b>Confiance</b>: {self.confiance}"
            f"{f' (calibree: {self.confiance_calibree})' if self.confiance_calibree is not None else ''}%\n"
            f"<b>Exploit.</b>  : {self.exploitability_statut}\n"
            f"<b>Regime</b>   : {self.regime_type or 'n/a'}\n"
            f"<b>Bayes</b>    : {self.predictor_action or 'n/a'}"
            f"{f' (edge: {self.predictor_edge_pips:+.1f} pips)' if self.predictor_edge_pips is not None else ''}\n"
            f"\n"
            f"<b>Principes</b>: {principles_str}\n"
            f"\n"
            f"<b>UTC</b>      : {self.timestamp}\n"
            f"<b>ID</b>       : <code>{self.signal_id}</code>"
        )

    def format_console(self) -> str:
        return (
            f"[SIGNAL V9] {self.symbol} {self.timeframe} "
            f"{self.direction.upper()} conf={self.confiance} "
            f"exploit={self.exploitability_statut} "
            f"regime={self.regime_type} "
            f"bayes={self.predictor_action}({self.predictor_edge_pips}) "
            f"id={self.signal_id} utc={self.timestamp}"
        )


# ── Telegram send (R6 fail-open) ───────────────────────────────────────
def send_telegram(msg: str) -> bool:
    """Envoie via Telegram. R6 : retourne False silencieusement si KO."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        # Utilise le module canonique scripts/v9_telegram_notifier.py
        # (cohérent avec decision_logger.py ligne 185)
        from scripts.v9_telegram_notifier import send_telegram as _send  # type: ignore
        cfg = {"token": TELEGRAM_BOT_TOKEN, "chat_id": TELEGRAM_CHAT_ID}
        return bool(_send(msg, cfg, timeout=5))
    except Exception as exc:
        log.warning("telegram send failed: %s", exc)
        return False


def dispatch(alert: SignalAlert) -> bool:
    """Envoie l'alerte via Telegram (live) ou log console (fail-open)."""
    text = alert.format_telegram()
    sent = send_telegram(text)
    if sent:
        log.info("TELEGRAM SENT: %s %s %s conf=%d",
                 alert.symbol, alert.timeframe, alert.direction, alert.confiance)
    else:
        # R6 fail-open : log console + buffer
        console_line = alert.format_console()
        log.info("[CONSOLE] %s", console_line)
        _console_buffer.append(console_line)
    return sent


# ── SQL query ──────────────────────────────────────────────────────────
# Critère "vraie entrée" reconstruit depuis champs requêtables :
#   - direction IN (haussiere, baissiere)   → signal directionnel
#   - confiance >= RISK_CONFIANCE_MIN       → passe RiskManager
#   - exploitability_statut = exploitable   → fenêtre tradable
# On déduplique via signal_id (clé naturelle unique dans la table).
QUERY_VRAIE_ENTREE = """
    SELECT signal_id, symbol, timeframe, direction, confiance,
           confiance_calibree, exploitability_statut, regime_type,
           predictor_action, predictor_edge_pips, timestamp,
           principes_source_json
    FROM signals
    WHERE direction IN ('haussiere', 'baissiere')
      AND confiance >= ?
      AND exploitability_statut = 'exploitable'
      AND timestamp > ?
    ORDER BY timestamp ASC
    LIMIT 50
"""


def fetch_new_signals(seen: set[str]) -> list[SignalAlert]:
    """Récupère les nouveaux signaux 'vraie entrée' non encore alertés."""
    now = int(time.time())
    cutoff = datetime.fromtimestamp(now - LOOKBACK_SEC, tz=timezone.utc).isoformat()
    alerts: list[SignalAlert] = []
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            QUERY_VRAIE_ENTREE,
            (RISK_CONFIANCE_MIN, cutoff),
        ).fetchall()
        conn.close()
    except sqlite3.OperationalError as exc:
        log.error("DB read error: %s", exc)
        return alerts

    for row in rows:
        if row["signal_id"] in seen:
            continue
        seen.add(row["signal_id"])
        # Parse principes_source_json (stocké comme JSON array string)
        principles: list[str] = []
        try:
            raw_p = row["principes_source_json"]
            if raw_p:
                parsed = json.loads(raw_p)
                if isinstance(parsed, list):
                    principles = [str(p) for p in parsed]
        except (json.JSONDecodeError, TypeError):
            pass
        alerts.append(SignalAlert(
            signal_id=row["signal_id"],
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            direction=row["direction"],
            confiance=row["confiance"],
            confiance_calibree=row["confiance_calibree"],
            exploitability_statut=row["exploitability_statut"],
            regime_type=row["regime_type"],
            predictor_action=row["predictor_action"],
            predictor_edge_pips=row["predictor_edge_pips"],
            timestamp=row["timestamp"],
            principles=principles,
        ))
    return alerts


# ── Boucle principale ─────────────────────────────────────────────────
def main() -> int:
    if not DB_PATH.exists():
        log.error("DB introuvable: %s — sortir.", DB_PATH)
        return 1

    log.info("=" * 60)
    log.info("v9_signal_alerter (Phase 179)")
    log.info("=" * 60)
    log.info("DB          : %s", DB_PATH)
    log.info("Poll        : %ds", POLL_SEC)
    log.info("Lookback    : %ds", LOOKBACK_SEC)
    log.info("Confiance   : >= %d (RiskManager)", RISK_CONFIANCE_MIN)
    log.info("Telegram    : %s",
             "ENABLED" if (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
             else "DISABLED (R6 fail-open, console only)")
    if TELEGRAM_BOT_TOKEN:
        log.info("Bot token   : ***%s", TELEGRAM_BOT_TOKEN[-8:])
    if TELEGRAM_CHAT_ID:
        log.info("Chat ID     : %s", TELEGRAM_CHAT_ID)
    log.info("=" * 60)

    seen: set[str] = set()
    poll_count = 0
    alert_count = 0
    while True:
        try:
            new_alerts = fetch_new_signals(seen)
            for a in new_alerts:
                dispatch(a)
                alert_count += 1
        except KeyboardInterrupt:
            log.info("Interruption manuelle (Ctrl+C). Bilan: %d alertes envoyees sur %d polls.",
                     alert_count, poll_count)
            return 0
        except Exception as exc:  # R6
            log.exception("poll error: %s", exc)
        poll_count += 1
        if poll_count % 12 == 0:  # log toutes les 60s
            log.info("heartbeat: %d polls, %d alertes envoyees, %d vus en memoire",
                     poll_count, alert_count, len(seen))
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
