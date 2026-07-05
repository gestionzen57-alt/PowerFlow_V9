#!/usr/bin/env python3
"""v9_market_open.py — Procédure d'ouverture marché PowerFlow V9 (--market-open).

Automatise la partie mécanique de
`workspace/perplexity/assets/MARKET_OPEN_TEMPLATE.md` (T-30/T0) : réutilise
la séquence `v9_bootstrap.run_boot` (checks bloquants, port stale, démarrage
serveur), puis ajoute les vérifications propres à l'ouverture marché :
statut calendrier (`core/v9/market_calendar.py`), plausibilité AUD
(doit rester entre EUR et NZD ± 15 unités — détecte une inversion de buffer
SDI, cf. gabarit), et taux de stale. Termine par un mini-checkpoint
pré-rempli pour les sections T-30/T0 (les sections T+15/T+60 restent à la
charge de l'opérateur, car elles exigent d'attendre le temps réel écoulé et
un jugement humain — non automatisables sans dénaturer l'observation).

Couche cognitive : outillage d'observation uniquement. Aucune logique de
trading, aucune décision, aucune modification de `core/v9/*`. Ne remplace
pas `scripts/validate_ea_output.py` ni `scripts/live_integration_test.py`,
que l'opérateur reste libre de lancer en complément (voir le runbook).

Usage :
    python scripts/v9_market_open.py --market-open
    python scripts/v9_market_open.py --market-open --aud-tolerance 15
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH  # noqa: E402
from scripts.v9_bootstrap import run_boot  # noqa: E402
from scripts.v9_supervisor import (  # noqa: E402
    generate_mini_checkpoint,
    health_snapshot_to_observed_lines,
    read_health_snapshot,
    setup_logging,
)

DEFAULT_AUD_TOLERANCE = 15.0


def latest_forces_row() -> dict | None:
    """Dernière ligne `forces_snapshots` toutes timeframes confondues,
    lecture seule. None si la DB ou la table n'existe pas encore."""
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM forces_snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    conn.close()
    return dict(row) if row else None


def check_aud_plausibility(row: dict, tolerance: float = DEFAULT_AUD_TOLERANCE) -> tuple[bool, str]:
    """AUD doit rester entre EUR et NZD (± tolerance) — un AUD hors de cet
    intervalle signale une inversion probable de buffer SDI (voir
    `ea/V9_Sonde_README.md` section 4). Retourne (plausible, message)."""
    for key in ("force_eur", "force_nzd", "force_aud"):
        if key not in row or row[key] is None:
            return True, f"Verification ignoree ({key} absent du dernier snapshot)."
    eur, nzd, aud = row["force_eur"], row["force_nzd"], row["force_aud"]
    low, high = sorted((eur, nzd))
    plausible = (low - tolerance) <= aud <= (high + tolerance)
    if plausible:
        return True, f"AUD={aud:.1f} plausible (EUR={eur:.1f}, NZD={nzd:.1f}, tolerance={tolerance:.0f})."
    return False, (
        f"AUD={aud:.1f} HORS INTERVALLE (EUR={eur:.1f}, NZD={nzd:.1f}, "
        f"tolerance={tolerance:.0f}) — inversion de buffer SDI possible, "
        f"voir ea/V9_Sonde_README.md section 4."
    )


def stale_rate() -> tuple[int, int, float]:
    """(total, stale, taux%) sur `forces_snapshots`. (0, 0, 0.0) si absent."""
    if not DB_PATH.exists():
        return 0, 0, 0.0
    conn = sqlite3.connect(str(DB_PATH))
    try:
        total = conn.execute("SELECT COUNT(*) FROM forces_snapshots").fetchone()[0]
        stale = conn.execute("SELECT COUNT(*) FROM forces_snapshots WHERE stale = 1").fetchone()[0]
    except sqlite3.OperationalError:
        total, stale = 0, 0
    conn.close()
    rate = (stale / total * 100) if total else 0.0
    return total, stale, rate


def run_market_open(aud_tolerance: float = DEFAULT_AUD_TOLERANCE) -> int:
    logger = setup_logging("v9.market_open")
    logger.info("=== Demarrage procedure --market-open ===")

    now_snapshot = read_health_snapshot()
    if not now_snapshot["market_open"]:
        logger.warning(
            "Marche annonce FERME a l'instant present — la procedure continue "
            "(preparation avant ouverture reelle possible), mais aucune donnee "
            "EA n'est attendue tant que le marche n'a pas ouvert."
        )
        if now_snapshot.get("market_status_warning"):
            logger.warning(
                f"Divergence calendrier/activite live : {now_snapshot['market_status_warning']}"
            )
    else:
        logger.info(f"Marche OUVERT (session: {now_snapshot['market_session']}).")

    boot_rc = run_boot(write_checkpoint=False)
    if boot_rc != 0:
        logger.error("Sequence de boot (checks/port/serveur) en echec — arret de --market-open.")
        return boot_rc

    post_snapshot = read_health_snapshot()
    observed = health_snapshot_to_observed_lines(post_snapshot)

    row = latest_forces_row()
    ecart_lines = []
    if row is not None:
        aud_ok, aud_msg = check_aud_plausibility(row, tolerance=aud_tolerance)
        logger.info(aud_msg) if aud_ok else logger.warning(aud_msg)
        observed.append(f"Plausibilite AUD : {aud_msg}")
        if not aud_ok:
            ecart_lines.append(aud_msg)
    else:
        logger.info("Aucun snapshot recu pour l'instant (marche ferme ou EA non lance).")
        observed.append("Aucun snapshot forces_snapshots recu pour l'instant.")

    total, stale, rate = stale_rate()
    observed.append(f"Taux de stale : {stale}/{total} ({rate:.1f}%)")
    logger.info(f"Taux de stale : {stale}/{total} ({rate:.1f}%)")

    ecart = "\n".join(f"- {line}" for line in ecart_lines) if ecart_lines else (
        "Aucun ecart releve automatiquement — a completer par l'operateur si pertinent."
    )

    checkpoint_path = generate_mini_checkpoint(
        kind="market_open",
        contexte=(
            "Ouverture marche automatisee (scripts/v9_market_open.py --market-open) — "
            "sections T-30/T0 pre-remplies ; T+15/T+60 a completer par l'operateur "
            "(voir MARKET_OPEN_TEMPLATE.md)."
        ),
        observed_lines=observed,
        ecart=ecart,
        suite=(
            "Completer T+15 (scripts/v9_dashboard.py --watch comportements, "
            "scripts/live_integration_test.py) et T+60 (scripts/v9_dashboard.py "
            "--watch signals/decisions, scripts/v9_calibration.py --stats) "
            "manuellement selon MARKET_OPEN_TEMPLATE.md."
        ),
    )
    logger.info(f"Mini-checkpoint ecrit : {checkpoint_path}")
    logger.info("=== --market-open termine (T-30/T0) ===")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Procedure d'ouverture marche PowerFlow V9")
    parser.add_argument("--market-open", action="store_true", help="Executer la procedure (requis)")
    parser.add_argument(
        "--aud-tolerance", type=float, default=DEFAULT_AUD_TOLERANCE,
        help=f"Tolerance de plausibilite AUD en unites de force (defaut: {DEFAULT_AUD_TOLERANCE:.0f})",
    )
    args = parser.parse_args()

    if not args.market_open:
        parser.error("--market-open est requis")
    return run_market_open(aud_tolerance=args.aud_tolerance)


if __name__ == "__main__":
    sys.exit(main())
