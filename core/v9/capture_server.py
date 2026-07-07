#!/usr/bin/env python3
"""capture_server.py — Serveur TCP réception forces MT4 → v9_forces.db.

Écoute TCP 127.0.0.1:31685, reçoit le JSON brut de la sonde EA MT4
(ea/V9_Sonde_TF.mq4), le transforme via ForcesReader (STALE_GATE inclus)
et insère chaque ligne dans forces_snapshots (data/v9_forces.db).

Couche cognitive : capture uniquement. Aucune logique de trading,
aucune décision, aucune interprétation au-delà de FORMAT_FORCES.md.

Usage :
    python -m core.v9.capture_server              # daemon
    python -m core.v9.capture_server --once        # 1 message puis exit
    python -m core.v9.capture_server --status       # état DB + stats
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time

from core.v9.config import ENABLE_CHAIN, LISTEN_HOST, LISTEN_PORT, LOG_PATH, DB_PATH
from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db
from core.v9.forces_reader import ForcesReader, ForcesReaderError
from core.v9.orchestrator import run_chain


def setup_logging() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    # F-13 (2026-07-07) : rotation logs. RotatingFileHandler évite que
    # logs/v9_capture.log grossisse indéfiniment. 10 MB × 5 backups = 50 MB max.
    from logging.handlers import RotatingFileHandler
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            RotatingFileHandler(
                LOG_PATH,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
                encoding="utf-8",
            ),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("v9.capture_server")


log = setup_logging()


class Stats:
    def __init__(self) -> None:
        self.received = 0
        self.inserted = 0
        self.stale = 0
        self.errors = 0
        self.chain_ok = 0
        self.chain_errors = 0
        self.start_time = time.time()

    def summary(self) -> str:
        elapsed = time.time() - self.start_time
        rate = self.inserted / elapsed * 60 if elapsed > 0 else 0.0
        return (
            f"Stats: recus={self.received} inseres={self.inserted} "
            f"stale={self.stale} erreurs={self.errors} ({rate:.1f}/min) "
            f"chaine_ok={self.chain_ok} chaine_erreurs={self.chain_errors}"
        )


stats = Stats()
reader = ForcesReader()


def insert_row(row: dict) -> bool:
    """Insère une ligne transformée dans forces_snapshots (INSERT OR IGNORE)."""
    try:
        conn = get_connection()
        values = [row.get(col) for col in FORCES_COLUMNS]
        placeholders = ", ".join(["?"] * len(FORCES_COLUMNS))
        col_names = ", ".join(FORCES_COLUMNS)
        conn.execute(
            f"INSERT OR IGNORE INTO forces_snapshots ({col_names}) VALUES ({placeholders})",
            values,
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        log.exception("DB insert error")
        return False


async def handle_client(reader_stream: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Traite une connexion EA MT4 (1 message puis déconnexion)."""
    addr = writer.get_extra_info("peername")
    try:
        data = await reader_stream.read(8192)
        if not data:
            return

        raw_text = data.decode("utf-8", errors="replace").strip()
        stats.received += 1

        try:
            raw = json.loads(raw_text)
        except json.JSONDecodeError as e:
            log.warning("JSON invalide de %s: %s | raw=%s", addr, e, raw_text[:200])
            stats.errors += 1
            return

        try:
            result = reader.transform(raw)
        except ForcesReaderError as e:
            log.warning("Validation echouee de %s: %s | raw=%s", addr, e, raw_text[:200])
            stats.errors += 1
            return

        row = result["row"]
        if row["stale"]:
            stats.stale += 1

        if insert_row(row):
            stats.inserted += 1
            if stats.inserted % 60 == 0:
                log.info(stats.summary())

            if ENABLE_CHAIN and not row["stale"]:
                # Sprint V9 2026-07-07 — Hook télémétrie par agent.
                # Telemetry best-effort : ne doit JAMAIS casser le chemin chaud.
                chain_t0 = time.perf_counter()
                try:
                    from core.v9.agent_telemetry import record as _tel_record
                    _tel_record(
                        agent_name="orchestrator",
                        snapshot_id=row["snapshot_id"],
                        status="OK",
                    )
                except Exception:
                    log.exception("telemetry init fail (best-effort)")
                try:
                    chain_result = run_chain(row["snapshot_id"])
                    if chain_result["error"] is None:
                        stats.chain_ok += 1
                        _chain_status = "OK"
                    else:
                        stats.chain_errors += 1
                        _chain_status = f"ERROR:{chain_result['error']}"
                except Exception:
                    log.exception("Erreur inattendue orchestrateur pour %s", row["snapshot_id"])
                    stats.chain_errors += 1
                    _chain_status = "ERROR:unhandled"
                try:
                    from core.v9.agent_telemetry import record as _tel_record2
                    _tel_record2(
                        agent_name="orchestrator",
                        snapshot_id=row["snapshot_id"],
                        latency_ms=(time.perf_counter() - chain_t0) * 1000,
                        status=_chain_status,
                    )
                except Exception:
                    log.exception("telemetry log fail (best-effort)")
        else:
            stats.errors += 1

    except Exception:
        log.exception("Erreur handle_client")
        stats.errors += 1
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def run_server(once: bool = False) -> None:
    init_db()

    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM forces_snapshots").fetchone()[0]
    conn.close()
    log.info("DB: %s (%d snapshots)", DB_PATH, count)
    log.info("Ecoute TCP %s:%d", LISTEN_HOST, LISTEN_PORT)

    if once:
        done = asyncio.Event()

        async def handle_once(r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
            await handle_client(r, w)
            done.set()

        server = await asyncio.start_server(handle_once, LISTEN_HOST, LISTEN_PORT)
        async with server:
            await done.wait()
        return

    server = await asyncio.start_server(handle_client, LISTEN_HOST, LISTEN_PORT)
    async with server:
        await server.serve_forever()


def show_status() -> None:
    if not DB_PATH.exists():
        print(f"DB introuvable: {DB_PATH}")
        return

    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM forces_snapshots").fetchone()[0]
    stale_count = conn.execute(
        "SELECT COUNT(*) FROM forces_snapshots WHERE stale = 1"
    ).fetchone()[0]
    last = conn.execute(
        "SELECT created_at, symbol, timeframe, direction, force_usd, force_eur, stale "
        "FROM forces_snapshots ORDER BY id DESC LIMIT 1"
    ).fetchone()
    recent = conn.execute(
        "SELECT COUNT(*) FROM forces_snapshots WHERE created_at > datetime('now', '-1 day')"
    ).fetchone()[0]
    conn.close()

    print(f"DB: {DB_PATH}")
    print(f"Total snapshots: {count}")
    print(f"Stale snapshots: {stale_count}")
    print(f"Dernieres 24h: {recent}")
    if last:
        print(
            f"Dernier: {last[0]} {last[1]} tf={last[2]} direction={last[3]} "
            f"USD={last[4]} EUR={last[5]} stale={bool(last[6])}"
        )
    print(stats.summary())
    print(f"Stale par timeframe: {reader.stale_stats()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture forces MT4 -> v9_forces.db")
    parser.add_argument("--once", action="store_true", help="Recevoir 1 message puis exit")
    parser.add_argument("--status", action="store_true", help="Afficher le statut de la DB")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    log.info("=" * 50)
    log.info("Capture Forces - PowerFlow V9")
    log.info("=" * 50)

    try:
        asyncio.run(run_server(once=args.once))
    except KeyboardInterrupt:
        log.info("Arret. %s", stats.summary())


if __name__ == "__main__":
    main()
