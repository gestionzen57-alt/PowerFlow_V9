#!/usr/bin/env python3
"""validate_ea_output.py — Valide le JSON brut envoyé par la sonde EA MT4.

Reçoit 1 message TCP (format ea/V9_Sonde_TF.mq4 ou ea/V9_Sonde_M1.mq4),
vérifie sa conformité à docs/architecture/formats/FORMAT_FORCES.md et affiche
un rapport de validation. N'écrit rien en base — outil de diagnostic terrain
uniquement.

Si le serveur de capture est déjà actif (port occupé), lit le dernier
snapshot depuis la base de données — plus fiable que tenter un bind
concurrent sur Windows (WinError 10013).

Couche cognitive : validation de capture. Aucune logique de trading, aucune
décision, aucune interprétation au-delà du format attendu.

Usage :
    python scripts/validate_ea_output.py --once                 # TCP si port libre, sinon DB
    python scripts/validate_ea_output.py --once --force-tcp     # force le mode TCP
    python scripts/validate_ea_output.py --once --from-db       # force la lecture DB
"""

from __future__ import annotations

import argparse
import json
import math
import socket
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DEVISES, LISTEN_HOST, LISTEN_PORT, TIMEFRAME_TICK, TIMEFRAMES_CANDLE  # noqa: E402
from core.v9.market_calendar import MarketCalendar  # noqa: E402

REQUIRED_BASE_FIELDS = ["schema_version", "symbol", "timeframe", "bridge_version"]
FORCE_KEYS = [f"force_{d.lower()}" for d in DEVISES]

# Tolérance (secondes) entre timestamp UTC déclaré et capture_time broker
# reconverti en UTC, pour absorber la latence réseau + arrondi ISO8601.
TIMESTAMP_TOLERANCE_S = 5.0

# Tolérance (unités de force) pour la vérification de plausibilité AUD.
AUD_BETWEEN_EUR_NZD_TOLERANCE = 15.0


def receive_one_message(port: int, host: str = LISTEN_HOST, timeout_s: float | None = None) -> str:
    """Tente de recevoir un message EA via TCP.

    Si le port est déjà occupé (serveur de capture actif), retourne None
    pour signaler au main() de basculer en mode DB.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError as exc:
        sock.close()
        print(f"Port {host}:{port} deja occupe par le serveur de capture.")
        print(f"Fallback : lecture du dernier snapshot depuis la base de donnees.")
        return None  # signal fallback DB
    sock.listen(1)
    print(f"En attente d'un message EA sur {host}:{port}...")
    if timeout_s is not None:
        sock.settimeout(timeout_s)
    try:
        conn, addr = sock.accept()
    finally:
        sock.close()
    print(f"Connexion recue de {addr}")
    with conn:
        data = conn.recv(65536)
    return data.decode("utf-8", errors="replace").strip()


def validate_structure(raw: dict) -> list[str]:
    """Retourne la liste des erreurs structurelles (vide si valide)."""
    errors = []
    for field in REQUIRED_BASE_FIELDS:
        if field not in raw:
            errors.append(f"champ obligatoire manquant : {field}")

    timeframe = str(raw.get("timeframe", ""))
    if timeframe not in TIMEFRAMES_CANDLE and timeframe not in TIMEFRAME_TICK:
        errors.append(f"timeframe inconnu : {timeframe!r}")

    if "timestamp" not in raw and "capture_time" not in raw:
        errors.append("aucun horodatage exploitable (timestamp ou capture_time requis)")

    missing_forces = [k for k in FORCE_KEYS if k not in raw]
    if missing_forces:
        errors.append(f"forces manquantes : {missing_forces}")
    return errors


def validate_forces_values(raw: dict) -> tuple[dict[str, float], list[str]]:
    """Vérifie que les 8 forces sont présentes, non nulles, non NaN."""
    warnings = []
    forces: dict[str, float] = {}
    for devise in DEVISES:
        key = f"force_{devise.lower()}"
        value = raw.get(key)
        if value is None:
            warnings.append(f"{key} absent")
            continue
        try:
            fvalue = float(value)
        except (TypeError, ValueError):
            warnings.append(f"{key} non numerique : {value!r}")
            continue
        if math.isnan(fvalue):
            warnings.append(f"{key} est NaN")
        elif fvalue == 0.0:
            warnings.append(f"{key} est a zero (suspect si persistant)")
        forces[devise] = fvalue
    return forces, warnings


def validate_timestamp(raw: dict) -> list[str]:
    warnings = []
    timestamp_str = raw.get("timestamp")
    capture_time = raw.get("capture_time")

    if timestamp_str is None:
        warnings.append("champ 'timestamp' (UTC) absent, impossible de verifier le decalage broker")
        return warnings

    try:
        declared = datetime.fromisoformat(str(timestamp_str).replace("Z", "+00:00"))
    except ValueError:
        warnings.append(f"'timestamp' non parsable en ISO8601 : {timestamp_str!r}")
        return warnings

    if capture_time is None:
        return warnings

    try:
        broker_dt = datetime.fromtimestamp(int(capture_time), tz=timezone.utc).replace(tzinfo=None)
        expected_utc = MarketCalendar.broker_to_utc(broker_dt)
    except (TypeError, ValueError, OSError):
        warnings.append(f"'capture_time' non exploitable : {capture_time!r}")
        return warnings

    delta_s = abs((declared.replace(tzinfo=None) - expected_utc.replace(tzinfo=None)).total_seconds())
    if delta_s > TIMESTAMP_TOLERANCE_S:
        warnings.append(
            f"ecart timestamp/broker suspect : {delta_s:.1f}s "
            f"(timestamp={declared.isoformat()} vs capture_time converti={expected_utc.isoformat()}) "
            f"- verifier BrokerUTCOffsetHours sur l'EA"
        )
    return warnings


def check_aud_plausibility(forces: dict[str, float]) -> list[str]:
    """AUD doit normalement se situer entre EUR et NZD (heuristique de
    plausibilite, pas une regle stricte) — sert a detecter un buffer AUD
    potentiellement inverse sur l'indicateur SDI."""
    warnings = []
    if not all(d in forces for d in ("AUD", "EUR", "NZD")):
        return warnings
    aud, eur, nzd = forces["AUD"], forces["EUR"], forces["NZD"]
    low, high = min(eur, nzd), max(eur, nzd)
    if not (low - AUD_BETWEEN_EUR_NZD_TOLERANCE <= aud <= high + AUD_BETWEEN_EUR_NZD_TOLERANCE):
        warnings.append(
            f"AUD ({aud:.2f}) hors de l'intervalle EUR/NZD ([{low:.2f}, {high:.2f}] "
            f"+/-{AUD_BETWEEN_EUR_NZD_TOLERANCE}) - AUD potentiellement inverse, "
            f"voir ea/V9_Sonde_README.md section 4 (diagnostic buffers SDI)"
        )
    return warnings


def print_report(raw: dict, struct_errors: list[str], forces: dict[str, float],
                  force_warnings: list[str], ts_warnings: list[str], aud_warnings: list[str]) -> bool:
    print("=" * 60)
    print("Rapport de validation - sortie EA MT4")
    print("=" * 60)
    print(f"symbol            : {raw.get('symbol')}")
    print(f"timeframe         : {raw.get('timeframe')}")
    print(f"bridge_version    : {raw.get('bridge_version')}")
    print(f"schema_version    : {raw.get('schema_version')}")
    print(f"timestamp (UTC)   : {raw.get('timestamp')}")
    print(f"is_closed_bar     : {raw.get('is_closed_bar')}")
    print()

    print("Format JSON        : OK (parse reussi)")
    print(f"Champs obligatoires: {'OK' if not struct_errors else 'ECHEC'}")
    for err in struct_errors:
        print(f"  - {err}")

    print(f"8 forces presentes : {'OK' if len(forces) == 8 else f'{len(forces)}/8'}")
    for devise in DEVISES:
        value = forces.get(devise)
        marker = "OK" if value is not None else "MANQUANT"
        print(f"  force_{devise.lower():<4} = {value if value is not None else '-':<10} [{marker}]")
    for warn in force_warnings:
        print(f"  [WARN] {warn}")

    print(f"Timestamp broker/UTC: {'OK' if not ts_warnings else 'WARN'}")
    for warn in ts_warnings:
        print(f"  [WARN] {warn}")

    print(f"Plausibilite AUD   : {'OK' if not aud_warnings else 'SUSPECT'}")
    for warn in aud_warnings:
        print(f"  [WARN] {warn}")

    print("-" * 60)
    passed = not struct_errors and len(forces) == 8
    print("RESULTAT : " + ("VALIDE" if passed else "INVALIDE"))
    if force_warnings or ts_warnings or aud_warnings:
        print("(avertissements non bloquants presents - voir details ci-dessus)")
    return passed


def _read_last_snapshot_from_db() -> str | None:
    """Lit le dernier snapshot forces_snapshots depuis la DB et le retourne
    comme JSON brut (simule le format EA). Utilisé en fallback quand le
    serveur de capture occupe déjà le port TCP."""
    import json as _json
    db_path = Path(__file__).resolve().parent.parent / "data" / "v9_forces.db"
    if not db_path.exists():
        print(f"Base de donnees introuvable : {db_path}")
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM forces_snapshots ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
    except sqlite3.OperationalError as exc:
        print(f"Erreur de lecture DB : {exc}")
        return None
    finally:
        conn.close()
    if row is None:
        print("Aucun snapshot trouve dans la base de donnees.")
        return None
    raw = dict(row)
    # Reconstruire le format attendu par validate_*
    result = {
        "schema_version": raw.get("schema_version", "1.0"),
        "symbol": raw.get("symbol"),
        "timeframe": raw.get("timeframe"),
        "bridge_version": raw.get("source", "MT4_SDI"),
        "timestamp": raw.get("timestamp"),
        "capture_time": raw.get("capture_time"),
        "is_closed_bar": raw.get("is_closed_bar"),
    }
    for d in ["USD", "GBP", "EUR", "JPY", "CAD", "CHF", "AUD", "NZD"]:
        result[f"force_{d.lower()}"] = raw.get(f"force_{d.lower()}")
    return _json.dumps(result, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Valide le JSON de sortie de la sonde EA MT4")
    parser.add_argument("--port", type=int, default=LISTEN_PORT, help=f"Port TCP d'ecoute (defaut: {LISTEN_PORT})")
    parser.add_argument("--host", default=LISTEN_HOST, help=f"Host d'ecoute (defaut: {LISTEN_HOST})")
    parser.add_argument("--once", action="store_true", help="Recevoir 1 message puis quitter (seul mode supporte)")
    parser.add_argument("--timeout", type=float, default=None, help="Timeout en secondes pour recevoir un message")
    parser.add_argument("--force-tcp", action="store_true", help="Force le mode TCP (echoue si port occupe)")
    parser.add_argument("--from-db", action="store_true", help="Force la lecture du dernier snapshot depuis la DB")
    args = parser.parse_args()

    if not args.once:
        print("Seul le mode --once est supporte.")
        return 1

    # Mode DB (force ou fallback)
    if args.from_db:
        raw_text = _read_last_snapshot_from_db()
        if raw_text is None:
            return 1
    elif not args.force_tcp:
        # Tentative TCP, fallback DB si port occupe
        try:
            raw_text = receive_one_message(args.port, args.host, args.timeout)
        except socket.timeout:
            print(f"Timeout : aucun message recu en {args.timeout}s.")
            return 1
        except OSError as exc:
            print(f"Erreur reseau : {exc}")
            return 1
        if raw_text is None:
            raw_text = _read_last_snapshot_from_db()
            if raw_text is None:
                return 1
    else:
        # Mode TCP force
        try:
            raw_text = receive_one_message(args.port, args.host, args.timeout)
        except socket.timeout:
            print(f"Timeout : aucun message recu en {args.timeout}s.")
            return 1
        except OSError as exc:
            print(f"Erreur reseau : {exc}")
            return 1
        if raw_text is None:
            print("Port occupe et mode --force-tcp actif : abandon.")
            return 1

    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        print(f"JSON invalide : {exc}")
        print(f"Contenu brut (200 premiers caracteres) : {raw_text[:200]!r}")
        return 1

    struct_errors = validate_structure(raw)
    forces, force_warnings = validate_forces_values(raw)
    ts_warnings = validate_timestamp(raw)
    aud_warnings = check_aud_plausibility(forces)

    passed = print_report(raw, struct_errors, forces, force_warnings, ts_warnings, aud_warnings)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
