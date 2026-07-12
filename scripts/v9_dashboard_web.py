#!/usr/bin/env python3
"""v9_dashboard_web.py — Dashboard web HITL (Brief Q3, 2026-07-12).

Serveur HTTP(S) lecture seule sur `data/v9_forces.db`. Aucune dépendance
pip (V9 = 100% stdlib, cf. requirements.txt) : FastAPI n'est pas installé
dans cet environnement (`pip` lui-même absent du venv projet) et le
principe "0 dépendance runtime" est documenté comme délibéré, pas un
oubli — donc stdlib `http.server` + `ssl` plutôt qu'une nouvelle
dépendance. Documenté ici pour traçabilité (cf. DECISIONS_LOG Brief Q3).

Pages :
    /             — dernier snapshot/décision + P&L paper (lecture seule)
    /review       — file HITL confiance 40-65 / low_confidence_block
                    (POST écrit UNIQUEMENT dans hitl_reviews, jamais
                    dans `decisions` — cf. core/v9/hitl_reviews_db.py)
    /trades       — historique paper_trades
    /calibration  — principle_scores + stats par session

Sécurité :
    - Basic auth obligatoire (config/dashboard.json, gitignored — voir
      config/dashboard.json.example). Le serveur refuse de démarrer si
      la config est absente/invalide (pas de mode "sans auth").
    - HTTPS via certificat auto-signé, généré au premier lancement
      (openssl CLI requis — bundlé avec Git for Windows sur ce poste ;
      documenté comme prérequis opérateur si absent ailleurs).

Usage :
    python scripts/v9_dashboard_web.py                  # port 9090
    python scripts/v9_dashboard_web.py --port 8443
    V9_DASHBOARD_PORT=8443 python scripts/v9_dashboard_web.py
"""

from __future__ import annotations

import argparse
import base64
import hmac
import html
import json
import os
import ssl
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.dashboard_queries import (  # noqa: E402
    get_calibration_view,
    get_hitl_queue,
    get_home_snapshot,
    get_paper_trades,
)
from core.v9.hitl_reviews_db import insert_review  # noqa: E402

DEFAULT_PORT = 9090
DASHBOARD_AUTH_CONFIG = ROOT_DIR / "config" / "dashboard.json"
DASHBOARD_CERT_DIR = ROOT_DIR / "config" / "dashboard_certs"


# ── Auth (Basic, config gitignored — même convention que config/telegram.json) ──
def _load_dashboard_auth_safe(config_path: Path | None = None) -> dict[str, str] | None:
    """Charge config/dashboard.json sans jamais lever. None = config absente/invalide.

    Miroir de `decision_logger._load_telegram_config_safe` (Brief O3) : un
    échec de chargement ne doit jamais faire planter l'appelant, mais ici
    (contrairement à Telegram, best-effort) l'appelant DOIT refuser de
    démarrer si None — pas de service HTTP sans auth valide."""
    path = config_path or DASHBOARD_AUTH_CONFIG
    try:
        if not path.exists():
            return None
        cfg = json.loads(path.read_text(encoding="utf-8"))
        username = str(cfg.get("USERNAME", "")).strip()
        password = str(cfg.get("PASSWORD", "")).strip()
        if not username or not password:
            return None
        return {"username": username, "password": password}
    except Exception:
        return None


def _check_basic_auth(header_value: str | None, username: str, password: str) -> bool:
    """Vérifie un header `Authorization: Basic <b64>` en temps constant."""
    if not header_value or not header_value.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header_value[len("Basic ") :]).decode("utf-8")
        got_user, _, got_pass = decoded.partition(":")
    except Exception:
        return False
    user_ok = hmac.compare_digest(got_user, username)
    pass_ok = hmac.compare_digest(got_pass, password)
    return user_ok and pass_ok


# ── Certificat auto-signé (openssl CLI, aucune dépendance pip) ───────
def ensure_self_signed_cert(cert_dir: Path | None = None) -> tuple[Path, Path]:
    """Génère cert.pem/key.pem si absents. Nécessite `openssl` dans PATH —
    documenté comme prérequis opérateur (bundlé Git for Windows sur ce
    poste ; sur un VPS Linux, paquet standard `openssl`)."""
    d = cert_dir or DASHBOARD_CERT_DIR
    d.mkdir(parents=True, exist_ok=True)
    cert_path = d / "cert.pem"
    key_path = d / "key.pem"
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path

    try:
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-keyout", str(key_path), "-out", str(cert_path),
                "-days", "365", "-subj", "/CN=localhost",
            ],
            check=True, capture_output=True, timeout=30,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(
            "Impossible de générer un certificat auto-signé (openssl CLI introuvable ou en "
            f"échec) : {exc}. Fournir manuellement config/dashboard_certs/{{cert,key}}.pem "
            "ou installer openssl."
        ) from exc
    return cert_path, key_path


# ── HTML (pur, testable sans serveur live) ────────────────────────────
def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>V9 — {html.escape(title)}</title>"
        "<style>body{font-family:monospace;margin:2em;background:#111;color:#ddd}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #444;"
        "padding:4px 8px;text-align:left}a{color:#6cf}nav a{margin-right:1em}</style>"
        "</head><body><nav><a href='/'>Accueil</a><a href='/review'>Review HITL</a>"
        "<a href='/trades'>Trades</a><a href='/calibration'>Calibration</a></nav>"
        f"<h1>{html.escape(title)}</h1>{body}</body></html>"
    )


def render_home(data: dict[str, Any]) -> str:
    state = data.get("state") or {}
    pnl = data.get("paper_pnl") or {}
    decision = (state.get("decisions") or [None])[0] or {}
    body = (
        "<h2>Dernière décision</h2>"
        f"<pre>{html.escape(json.dumps(decision, indent=2, default=str))}</pre>"
        "<h2>P&amp;L paper (clôturés)</h2>"
        f"<table><tr><th>Trades</th><th>Wins</th><th>Losses</th>"
        f"<th>Pips totaux</th><th>Pips moy.</th></tr>"
        f"<tr><td>{pnl.get('n_trades', 0)}</td><td>{pnl.get('n_wins', 0)}</td>"
        f"<td>{pnl.get('n_losses', 0)}</td><td>{pnl.get('total_pips', 0)}</td>"
        f"<td>{pnl.get('avg_pips', 0)}</td></tr></table>"
    )
    return _page("Accueil", body)


def render_review(queue: list[dict[str, Any]]) -> str:
    rows = []
    for d in queue:
        last_review = (d.get("reviews") or [None])[0]
        status = html.escape(last_review["verdict"]) if last_review else "en attente"
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(d.get('decision_id')))}</td>"
            f"<td>{html.escape(str(d.get('timestamp')))}</td>"
            f"<td>{html.escape(str(d.get('symbol')))}</td>"
            f"<td>{html.escape(str(d.get('direction')))}</td>"
            f"<td>{d.get('confiance')}</td>"
            f"<td>{html.escape(d.get('tier', ''))}</td>"
            f"<td>{status}</td>"
            "<td>"
            "<form method='post' action='/review' style='display:inline'>"
            f"<input type='hidden' name='decision_id' value='{html.escape(str(d.get('decision_id')))}'>"
            "<input type='hidden' name='verdict' value='approved'>"
            "<button type='submit'>Approuver</button></form> "
            "<form method='post' action='/review' style='display:inline'>"
            f"<input type='hidden' name='decision_id' value='{html.escape(str(d.get('decision_id')))}'>"
            "<input type='hidden' name='verdict' value='rejected'>"
            "<button type='submit'>Rejeter</button></form>"
            "</td></tr>"
        )
    body = (
        "<p>Validation ici n'écrit jamais dans <code>decisions</code> — journal séparé "
        "<code>hitl_reviews</code> uniquement, sans effet sur RiskManager/CONFIANCE_MIN.</p>"
        "<table><tr><th>decision_id</th><th>timestamp</th><th>symbol</th><th>direction</th>"
        "<th>confiance</th><th>tier</th><th>dernière validation</th><th>action</th></tr>"
        + "".join(rows) + "</table>"
    )
    return _page("Review HITL", body)


def render_trades(trades: list[dict[str, Any]]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(t.get('trade_id')))}</td>"
        f"<td>{html.escape(str(t.get('direction')))}</td>"
        f"<td>{t.get('confiance')}</td>"
        f"<td>{html.escape(str(t.get('opened_at')))}</td>"
        f"<td>{html.escape(str(t.get('closed_at')))}</td>"
        f"<td>{t.get('pips_simulated')}</td>"
        f"<td>{'WIN' if t.get('is_win') == 1 else ('LOSS' if t.get('is_win') == 0 else '-')}</td>"
        "</tr>"
        for t in trades
    )
    body = (
        "<table><tr><th>trade_id</th><th>direction</th><th>confiance</th><th>opened_at</th>"
        "<th>closed_at</th><th>pips</th><th>résultat</th></tr>" + rows + "</table>"
    )
    return _page("Paper Trades", body)


def render_calibration(view: dict[str, Any]) -> str:
    buckets = view.get("session_buckets") or {}
    session_rows = "".join(
        f"<tr><td>{html.escape(session)}</td><td>{b.get('n')}</td>"
        f"<td>{b.get('wins')}</td><td>{b.get('wr_pct', '-')}</td></tr>"
        for session, b in buckets.items()
    )
    combo_rows = "".join(
        f"<tr><td>{html.escape(str(c.get('principle_id')))}</td><td>{c.get('n_trades')}</td>"
        f"<td>{c.get('win_rate')}</td><td>{c.get('avg_pips')}</td></tr>"
        for c in (view.get("top_combinations") or [])
    )
    body = (
        "<h2>WR par session (DYNAMIC)</h2>"
        "<table><tr><th>session</th><th>n</th><th>wins</th><th>WR%</th></tr>"
        + session_rows + "</table>"
        "<h2>Top combinaisons de principes</h2>"
        "<table><tr><th>principle_id</th><th>n_trades</th><th>win_rate</th><th>avg_pips</th></tr>"
        + combo_rows + "</table>"
    )
    return _page("Calibration", body)


# ── Serveur HTTP(S) ────────────────────────────────────────────────────
def make_handler(auth: dict[str, str], db_path: Path | None = None):
    class DashboardHandler(BaseHTTPRequestHandler):
        def _authorized(self) -> bool:
            return _check_basic_auth(
                self.headers.get("Authorization"), auth["username"], auth["password"]
            )

        def _require_auth(self) -> bool:
            if self._authorized():
                return True
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="V9 Dashboard"')
            self.end_headers()
            return False

        def _send_html(self, body: str, status: int = 200) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            if not self._require_auth():
                return
            try:
                if self.path == "/":
                    self._send_html(render_home(get_home_snapshot(db_path)))
                elif self.path == "/review":
                    self._send_html(render_review(get_hitl_queue(db_path)))
                elif self.path == "/trades":
                    self._send_html(render_trades(get_paper_trades(db_path)))
                elif self.path == "/calibration":
                    self._send_html(render_calibration(get_calibration_view(db_path)))
                else:
                    self._send_html(_page("404", "<p>Page inconnue.</p>"), status=404)
            except Exception as exc:  # jamais de stack trace exposée au client
                self._send_html(_page("Erreur", f"<p>Erreur interne : {html.escape(str(exc))}</p>"), status=500)

        def do_POST(self) -> None:  # noqa: N802
            if not self._require_auth():
                return
            if self.path != "/review":
                self._send_html(_page("404", "<p>Route POST inconnue.</p>"), status=404)
                return
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            fields = parse_qs(raw)
            decision_id = (fields.get("decision_id") or [""])[0]
            verdict = (fields.get("verdict") or [""])[0]
            try:
                insert_review(decision_id=decision_id, verdict=verdict, reviewer="dashboard_operator",
                               db_path=db_path)
                self.send_response(303)
                self.send_header("Location", "/review")
                self.end_headers()
            except ValueError as exc:
                self._send_html(_page("Erreur", f"<p>{html.escape(str(exc))}</p>"), status=400)

        def log_message(self, fmt: str, *args: Any) -> None:  # silence console par défaut
            pass

    return DashboardHandler


def run_server(port: int, host: str, db_path: Path | None = None) -> None:
    auth = _load_dashboard_auth_safe()
    if auth is None:
        print(
            "ERREUR : config/dashboard.json absent ou invalide (clés USERNAME/PASSWORD "
            "requises). Copier config/dashboard.json.example et le remplir. "
            "Le dashboard refuse de démarrer sans auth configurée.",
            file=sys.stderr,
        )
        sys.exit(1)

    cert_path, key_path = ensure_self_signed_cert()

    handler = make_handler(auth, db_path)
    httpd = ThreadingHTTPServer((host, port), handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)

    print(f"V9 Dashboard HTTPS sur https://{host}:{port}/ (Ctrl+C pour arrêter)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Dashboard web HITL V9 (lecture seule + review)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("V9_DASHBOARD_PORT", DEFAULT_PORT)))
    parser.add_argument("--host", default=os.environ.get("V9_DASHBOARD_HOST", "127.0.0.1"))
    args = parser.parse_args()
    run_server(args.port, args.host)
    return 0


if __name__ == "__main__":
    sys.exit(main())
