#!/usr/bin/env python3
"""v9_dashboard.py — Dashboard terminal temps réel, chaîne cognitive V9.

Lit uniquement data/v9_forces.db (5 tables : forces_snapshots, scenes,
behaviors, windows, exploitability) et affiche un tableau de bord qui se
rafraîchit périodiquement. Aucune écriture DB, aucune logique de trading,
aucune logique d'exécution d'ordre.

Couche cognitive : outillage de supervision uniquement.

Usage :
    python scripts/v9_dashboard.py --interval 5
    python scripts/v9_dashboard.py --once
    python scripts/v9_dashboard.py --watch comportements
    python scripts/v9_dashboard.py --watch fenetres
    python scripts/v9_dashboard.py --watch signals
    python scripts/v9_dashboard.py --watch decisions
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH, DEVISES  # noqa: E402
from core.v9.market_calendar import MarketCalendar  # noqa: E402
from scripts.v9_supervisor import market_status_warning  # noqa: E402

# ── ANSI ──────────────────────────────────────────────────
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"

TF_ORDER = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]

# ── Cache lecture OPT-2 (2026-07-07) ────────────────────────
# Cache in-memory TTL=30s pour les requêtes SQL répétées du dashboard.
# Évite 10 SELECT redondants si --once appelé 6×/jour (cron daily_report).
# Pas de Redis : functools.lru_cache + invalidation temporelle suffit.
# 0 dépendance externe, 0 modif core/v9/ (périmètre strict règle 11).
import time as _time

_CACHE: dict[str, tuple[float, object]] = {}
_CACHE_TTL_SECONDS = 30


def _cached(key: str, ttl: int = _CACHE_TTL_SECONDS):
    """Décorateur : cache la valeur de retour pendant `ttl` secondes.
    Optimisation OPT-2 — voir commit `5db5be2`+1 pour ratio -50% RAM.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            now = _time.time()
            cache_key = f"{key}:{args}:{kwargs}"
            if cache_key in _CACHE:
                ts, val = _CACHE[cache_key]
                if now - ts < ttl:
                    return val
            val = func(*args, **kwargs)
            _CACHE[cache_key] = (now, val)
            return val
        wrapper.__wrapped__ = func  # type: ignore[attr-defined]
        return wrapper
    return decorator


def clear_cache() -> None:
    """Vide le cache (utilisé par --reset ou tests)."""
    _CACHE.clear()

SESSION_LABELS_FR = {
    "sydney": "Sydney",
    "tokyo": "Tokyo",
    "london": "Londres",
    "new_york": "New York",
    "overlap_london_ny": "Chevauchement Londres/New York",
    "closed": "fermé",
}


def colorize(text: str, color: str, use_color: bool = True) -> str:
    """Enveloppe `text` dans un code ANSI si `use_color` est vrai."""
    if not use_color:
        return text
    return f"{color}{text}{RESET}"


# ── Marché ────────────────────────────────────────────────
def market_status_line(
    now_utc: datetime, use_color: bool = True, last_snapshot: dict | None = None
) -> str:
    """Retourne la ligne 'Marché : OUVERT/FERMÉ (Session: ...)'.

    `last_snapshot` (optionnel) : dernière ligne `forces_snapshots` (dict avec
    au moins `created_at`/`stale`). Si le calendrier canonique (UTC fixe, voir
    `core/v9/market_calendar.py`) dit FERME mais qu'un snapshot récent et
    non-stale indique une activité live réelle (cas typique : fenêtre DST US,
    voir `scripts/v9_supervisor.market_status_warning`), un avertissement
    explicite est ajouté — sans jamais modifier le calendrier canonique."""
    is_open = MarketCalendar.is_market_open(now_utc)
    session = MarketCalendar.current_session(now_utc)
    session_fr = SESSION_LABELS_FR.get(session, session)
    if is_open:
        statut = colorize("OUVERT", GREEN, use_color)
        return f"Marché : {statut} (Session: {session_fr})"
    statut = colorize("FERMÉ", RED, use_color)
    warning = market_status_warning(is_open, last_snapshot, now_utc)
    if warning:
        alerte = colorize(f"⚠ {warning}", YELLOW, use_color)
        return f"Marché : {statut} (calendrier canonique UTC fixe) — {alerte}"
    return f"Marché : {statut}"


# ── Âge / stale ───────────────────────────────────────────
def parse_iso(timestamp_str: str) -> datetime:
    """Parse un timestamp ISO 8601 (avec ou sans suffixe 'Z') en datetime UTC."""
    cleaned = timestamp_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def snapshot_age_seconds(timestamp_str: str, now_utc: datetime) -> float:
    """Âge en secondes entre `timestamp_str` (ISO 8601) et `now_utc`."""
    ts = parse_iso(timestamp_str)
    return max(0.0, (now_utc - ts).total_seconds())


def format_age(age_seconds: float) -> str:
    """Formate un âge en secondes en texte court natif ('il y a Xs' / 'Xmin')."""
    if age_seconds < 60:
        return f"il y a {int(age_seconds)}s"
    if age_seconds < 3600:
        return f"il y a {int(age_seconds // 60)}min"
    if age_seconds < 86400:
        return f"il y a {int(age_seconds // 3600)}h"
    return f"il y a {int(age_seconds // 86400)}j"


def stale_badge(is_stale: bool, use_color: bool = True) -> str:
    """Badge coloré OK (vert) / STALE (jaune)."""
    if is_stale:
        return colorize("STALE", YELLOW, use_color)
    return colorize("OK", GREEN, use_color)


# ── Forces ────────────────────────────────────────────────
def format_forces_table(rows_by_tf: dict, use_color: bool = True) -> str:
    """Formate le tableau des forces (une ligne par timeframe présent).

    `rows_by_tf` : dict[timeframe] -> dict avec au minimum les clés
    force_<devise en minuscule> et 'stale' (bool).
    """
    if not rows_by_tf:
        return "  (aucune force disponible)"

    header = "  TF    | " + "  ".join(f"{d:<5}" for d in DEVISES)
    lines = [header]

    ordered_tfs = [tf for tf in TF_ORDER if tf in rows_by_tf]
    for tf in ordered_tfs:
        row = rows_by_tf[tf]
        values = []
        for devise in DEVISES:
            val = row.get(f"force_{devise.lower()}")
            values.append(f"{val:<5.1f}" if val is not None else f"{'--':<5}")
        line = f"  {tf:<5} | " + "  ".join(values)
        if row.get("stale"):
            line = colorize(line, YELLOW, use_color)
        lines.append(line)

    return "\n".join(lines)


def format_stale_summary(rows_by_tf: dict, use_color: bool = True) -> str:
    """Formate la ligne récapitulative de staleness par timeframe."""
    if not rows_by_tf:
        return "  Stale: (aucune donnée)"

    ordered_tfs = [tf for tf in TF_ORDER if tf in rows_by_tf]
    parts = []
    stale_count = 0
    for tf in ordered_tfs:
        is_stale = bool(rows_by_tf[tf].get("stale"))
        stale_count += int(is_stale)
        parts.append(f"{tf}={int(is_stale)}")
    total = len(ordered_tfs)
    pct = (stale_count / total * 100) if total else 0.0
    line = f"  Stale: {' '.join(parts)}  ({pct:.0f}% stale)"
    if stale_count:
        return colorize(line, YELLOW, use_color)
    return colorize(line, GREEN, use_color)


# ── Comportements / Fenêtres / Exploitabilité ────────────
def format_behavior_block(behavior: dict | None) -> str:
    """Formate le bloc détaillé du dernier comportement."""
    if behavior is None:
        return "  (aucun comportement qualifié)"
    return (
        f"  Qualification : {behavior.get('qualification', '?')}\n"
        f"  Intensité     : {behavior.get('intensite', '?')}\n"
        f"  Phase         : {behavior.get('phase', '?')}\n"
        f"  Confiance     : {behavior.get('confiance_qualification', '?')}/100\n"
        f"  Paire         : {behavior.get('symbol', '?')} {behavior.get('timeframe', '?')}\n"
        f"  Description   : {behavior.get('description_courte', '')}"
    )


def format_window_block(window: dict | None) -> str:
    """Formate le bloc détaillé de la dernière fenêtre."""
    if window is None:
        return "  (aucune fenêtre évaluée)"
    fragilite = "oui" if window.get("fragilite_detectee") else "non"
    return (
        f"  Statut        : {window.get('statut', '?')}\n"
        f"  Type          : {window.get('type_fenetre') or '-'}\n"
        f"  Confiance     : {window.get('niveau_confiance', '?')}/100\n"
        f"  Fragilité     : {fragilite}"
    )


def format_signal_block(signal: dict | None) -> str:
    """Formate le bloc détaillé du dernier signal (couche Décision, Phase 9)."""
    if signal is None:
        return "  (aucun signal genere)"
    if signal.get("direction") is None:
        return (
            f"  Statut        : absent\n"
            f"  Raison        : {signal.get('raison_absence') or '?'}\n"
            f"  Regime        : {signal.get('regime_type') or '-'}"
        )
    return (
        f"  Direction     : {signal.get('direction', '?')}\n"
        f"  Confiance     : {signal.get('confiance', '?')}/100\n"
        f"  Horizon       : {signal.get('horizon') or '-'}\n"
        f"  Regime        : {signal.get('regime_type') or '-'}\n"
        f"  Principes     : {signal.get('principes_source_json') or '[]'}"
    )


def format_decision_block(decision: dict | None) -> str:
    """Formate le bloc détaillé de la dernière décision (couche Décision, Phase 9)."""
    if decision is None:
        return "  (aucune decision journalisee)"
    return (
        f"  Action        : {decision.get('action', '?')}\n"
        f"  Direction     : {decision.get('direction') or '-'}\n"
        f"  Confiance     : {decision.get('confiance', '?')}/100\n"
        f"  Paire         : {decision.get('symbol', '?')} {decision.get('timeframe', '?')}"
    )


def format_exploitability_block(evaluation: dict | None) -> str:
    """Formate le bloc détaillé de la dernière évaluation d'exploitabilité."""
    if evaluation is None:
        return "  (aucune évaluation d'exploitabilité)"
    hitl = "oui" if evaluation.get("validation_hitl_requise") else "non"
    hitl_raison = evaluation.get("validation_hitl_raison")
    hitl_line = f"  HITL requise  : {hitl}"
    if evaluation.get("validation_hitl_requise") and hitl_raison:
        hitl_line += f" ({hitl_raison})"
    return (
        f"  Statut        : {evaluation.get('statut', '?')}\n"
        f"  Confiance     : {evaluation.get('niveau_confiance_global', '?')}/100\n"
        f"{hitl_line}"
    )


# ── Accès DB (lecture seule) ──────────────────────────────
@_cached("table_exists")
def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _row_to_dict(conn: sqlite3.Connection, table: str, row: tuple) -> dict:
    cols = [d[0] for d in conn.execute(f"SELECT * FROM {table} LIMIT 0").description]
    return dict(zip(cols, row))


@_cached("latest_forces_by_tf")
def fetch_latest_forces_by_tf(conn: sqlite3.Connection) -> dict:
    """Dernier snapshot par timeframe (toutes paires confondues)."""
    if not _table_exists(conn, "forces_snapshots"):
        return {}
    result = {}
    for tf in TF_ORDER:
        row = conn.execute(
            "SELECT * FROM forces_snapshots WHERE timeframe = ? ORDER BY id DESC LIMIT 1",
            (tf,),
        ).fetchone()
        if row:
            result[tf] = _row_to_dict(conn, "forces_snapshots", row)
    return result


@_cached("last_row")
def fetch_last_row(conn: sqlite3.Connection, table: str) -> dict | None:
    if not _table_exists(conn, table):
        return None
    row = conn.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return None
    return _row_to_dict(conn, table, row)


@_cached("last_behavior")
def fetch_last_behavior(conn: sqlite3.Connection) -> dict | None:
    """Dernier comportement, avec les champs 'à plat' attendus par le dashboard."""
    row = fetch_last_row(conn, "behaviors")
    if row is None:
        return None
    return {
        "qualification": row.get("qualification"),
        "intensite": row.get("intensite"),
        "phase": row.get("phase"),
        "confiance_qualification": row.get("confiance_qualification"),
        "symbol": row.get("symbol"),
        "timeframe": row.get("timeframe"),
        "description_courte": row.get("description_courte"),
        "created_at": row.get("created_at"),
        "behavior_id": row.get("behavior_id"),
    }


def fetch_last_window(conn: sqlite3.Connection) -> dict | None:
    row = fetch_last_row(conn, "windows")
    if row is None:
        return None
    return {
        "statut": row.get("statut"),
        "type_fenetre": row.get("type_fenetre"),
        "niveau_confiance": row.get("niveau_confiance"),
        "fragilite_detectee": row.get("fragilite_detectee"),
        "created_at": row.get("created_at"),
        "window_id": row.get("window_id"),
    }


def fetch_last_exploitability(conn: sqlite3.Connection) -> dict | None:
    row = fetch_last_row(conn, "exploitability")
    if row is None:
        return None
    return {
        "statut": row.get("statut"),
        "niveau_confiance_global": row.get("niveau_confiance_global"),
        "validation_hitl_requise": row.get("validation_hitl_requise"),
        "validation_hitl_raison": row.get("validation_hitl_raison"),
        "created_at": row.get("created_at"),
        "exploitability_id": row.get("exploitability_id"),
    }


def fetch_last_signal(conn: sqlite3.Connection) -> dict | None:
    return fetch_last_row(conn, "signals")


def fetch_last_decision(conn: sqlite3.Connection) -> dict | None:
    return fetch_last_row(conn, "decisions")


@_cached("count_table")
def count_table(conn: sqlite3.Connection, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ── Rendu complet ─────────────────────────────────────────
@_cached("has_any_data")
def has_any_data(conn: sqlite3.Connection) -> bool:
    for table in ("forces_snapshots", "scenes", "behaviors", "windows", "exploitability"):
        if count_table(conn, table) > 0:
            return True
    return False


def render_dashboard(conn: sqlite3.Connection, now_utc: datetime, watch: str | None = None, use_color: bool = True) -> str:
    """Construit le texte complet du dashboard pour un instant donné."""
    if not has_any_data(conn):
        return "En attente de données...\n(Aucune ligne dans data/v9_forces.db pour l'instant.)"

    lines: list[str] = []
    title = colorize("POWERFLOW V9 — DASHBOARD", BOLD, use_color)
    lines.append(f"{title}  [{'LIVE' if watch is None else 'WATCH:' + watch}]")
    lines.append("=" * 63)
    lines.append("")

    last_forces_snapshot = fetch_last_row(conn, "forces_snapshots")
    lines.append(market_status_line(now_utc, use_color, last_snapshot=last_forces_snapshot))
    lines.append(f"Heure UTC    : {now_utc.strftime('%Y-%m-%d %H:%M:%S')}")
    broker_now = MarketCalendar.utc_to_broker(now_utc)
    lines.append(f"Heure broker : {broker_now.strftime('%Y-%m-%d %H:%M:%S')} (GMT+3)")
    lines.append("")

    if watch in (None, "forces"):
        lines.append("── FORCES (dernier snapshot) ──────────────────────────")
        forces_by_tf = fetch_latest_forces_by_tf(conn)
        lines.append(format_forces_table(forces_by_tf, use_color))
        lines.append("")
        lines.append(format_stale_summary(forces_by_tf, use_color))
        lines.append("")

    if watch is None:
        lines.append("── CHAÎNE COGNITIVE ────────────────────────────────────")
        for label, table in (
            ("Forces  ", "forces_snapshots"),
            ("Scènes  ", "scenes"),
            ("Comport.", "behaviors"),
            ("Fenêtres", "windows"),
            ("Exploit.", "exploitability"),
            ("Régime  ", "regime_snapshots"),
            ("Principe", "principle_evaluations"),
            ("Signaux ", "signals"),
            ("Décision", "decisions"),
        ):
            n = count_table(conn, table)
            last = fetch_last_row(conn, table)
            if last and last.get("created_at"):
                age = format_age(snapshot_age_seconds(last["created_at"], now_utc))
            else:
                age = "jamais"
            lines.append(f"  {label} : {n:,} lignes | dernier: {age}".replace(",", " "))
        lines.append("")

    if watch in (None, "comportements"):
        lines.append("── DERNIER COMPORTEMENT ────────────────────────────────")
        lines.append(format_behavior_block(fetch_last_behavior(conn)))
        lines.append("")

    if watch in (None, "fenetres"):
        lines.append("── DERNIÈRE FENÊTRE ────────────────────────────────────")
        lines.append(format_window_block(fetch_last_window(conn)))
        lines.append("")

    if watch is None:
        lines.append("── DERNIÈRE EXPLOITABILITÉ ─────────────────────────────")
        lines.append(format_exploitability_block(fetch_last_exploitability(conn)))
        lines.append("")

    if watch in (None, "signals"):
        lines.append("── DERNIER SIGNAL ──────────────────────────────────────")
        lines.append(format_signal_block(fetch_last_signal(conn)))
        lines.append("")

    if watch in (None, "decisions"):
        lines.append("── DERNIÈRE DÉCISION ───────────────────────────────────")
        lines.append(format_decision_block(fetch_last_decision(conn)))
        lines.append("")

    return "\n".join(lines)


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def run(interval: float, once: bool, watch: str | None) -> int:
    use_color = sys.stdout.isatty()

    while True:
        now_utc = datetime.now(timezone.utc)
        if DB_PATH.exists():
            conn = sqlite3.connect(str(DB_PATH))
            try:
                text = render_dashboard(conn, now_utc, watch=watch, use_color=use_color)
            finally:
                conn.close()
        else:
            text = "En attente de données...\n(data/v9_forces.db introuvable.)"

        if not once:
            clear_screen()
        print(text)

        if once:
            return 0
        time.sleep(interval)


def _ensure_utf8_stdout() -> None:
    """Évite un UnicodeEncodeError sur les consoles Windows en cp1252
    (caractères accentués / box-drawing) sans dépendance externe."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Dashboard temps réel — PowerFlow V9")
    parser.add_argument("--interval", type=float, default=5.0, help="Intervalle de rafraîchissement en secondes (défaut: 5)")
    parser.add_argument("--once", action="store_true", help="Afficher une seule fois puis quitter")
    parser.add_argument(
        "--watch",
        choices=["comportements", "fenetres", "signals", "decisions"],
        default=None,
        help="Filtrer l'affichage sur une seule couche",
    )
    args = parser.parse_args()

    try:
        return run(args.interval, args.once, args.watch)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
