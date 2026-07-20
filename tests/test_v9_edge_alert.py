"""test_v9_edge_alert.py — Régression pour v9_edge_alert.py (2026-07-20).

Vérifie que l'alerte :
  1. Détecte le pattern baissier 24h dégradé (WR < 40%, n >= 10, pips < -100)
  2. Détecte le pattern haussier 24h dégradé
  3. Liste les pires paires (pips <= -50)
  4. Respecte le rate-limit (1/pattern/6h)
  5. dry-run n'écrit PAS dans la state file

Doctrine :
- R7 : tests verts obligatoires
- R6 : helper défensif, n'appelle PAS Telegram en test
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def test_compute_edge_returns_expected_keys():
    """Vérifie la structure de l'edge snapshot."""
    from scripts.v9_edge_alert import _compute_edge
    edge = _compute_edge(ROOT_DIR / "data" / "v9_forces.db")
    assert "baissier_24h" in edge
    assert "haussier_24h" in edge
    assert "by_symbol_24h" in edge
    assert "timestamp" in edge
    b = edge["baissier_24h"]
    for k in ("n", "wins", "wr", "pips"):
        assert k in b, f"baissier_24h manque clé {k}"


def test_build_alerts_detects_baissier_24h_degraded():
    """Le pattern incident 2026-07-20 doit déclencher l'alerte baissier 24h."""
    from scripts.v9_edge_alert import _build_alerts, _compute_edge
    edge = _compute_edge(ROOT_DIR / "data" / "v9_forces.db")
    alerts = _build_alerts(edge)
    patterns = [a["pattern"] for a in alerts]
    assert "EDGE_BAISS_24H" in patterns, (
        f"Edge baissier 24h dégradé (WR 30%, -480 pips) doit déclencher "
        f"alerte. Patterns déclenchés : {patterns}"
    )


def test_build_alerts_includes_worst_pairs():
    """Les pires paires (pips < -50) doivent être listées."""
    from scripts.v9_edge_alert import _build_alerts, _compute_edge
    edge = _compute_edge(ROOT_DIR / "data" / "v9_forces.db")
    alerts = _build_alerts(edge)
    worst = [a for a in alerts if a["pattern"] == "WORST_PAIRS_24H"]
    assert len(worst) >= 1, "Au moins une alerte WORST_PAIRS attendue"
    # AUDUSD baissier -243 pips doit être dans le top
    pairs = worst[0]["data"]["pairs"]
    symbols_directions = [(p["symbol"], p["direction"]) for p in pairs]
    assert ("AUDUSD", "baissiere") in symbols_directions


def test_should_alert_respects_rate_limit(tmp_path: Path, monkeypatch):
    """1 alerte / pattern / 6h. State file persistant."""
    from scripts import v9_edge_alert
    monkeypatch.setattr(v9_edge_alert, "STATE_PATH", tmp_path / "state.json")
    state: dict = {"alerts": {}}
    # 1ère fois : doit alerter
    assert v9_edge_alert._should_alert(state, "TEST_PATTERN") is True
    # Après mark : ne doit plus alerter (dans la fenêtre 6h)
    v9_edge_alert._mark_alert(state, "TEST_PATTERN")
    assert v9_edge_alert._should_alert(state, "TEST_PATTERN") is False


def test_should_alert_resets_after_6h(tmp_path: Path, monkeypatch):
    """Au-delà de 6h, l'alerte peut re-déclencher."""
    from datetime import datetime, timezone, timedelta
    from scripts import v9_edge_alert
    monkeypatch.setattr(v9_edge_alert, "STATE_PATH", tmp_path / "state.json")
    old_time = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
    state = {"alerts": {"TEST_PATTERN": old_time}}
    assert v9_edge_alert._should_alert(state, "TEST_PATTERN") is True


def test_dry_run_does_not_modify_state(tmp_path: Path, monkeypatch, capsys):
    """dry-run doit afficher sans toucher la state file."""
    from scripts import v9_edge_alert
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(v9_edge_alert, "STATE_PATH", state_file)
    # Force au moins 1 alerte avec un état simulé
    monkeypatch.setattr(v9_edge_alert, "_compute_edge", lambda _db: {
        "timestamp": "2026-07-20T14:42:00+00:00",
        "baissier_24h": {"n": 50, "wins": 10, "wr": 20.0, "pips": -300.0},
        "haussier_24h": {"n": 50, "wins": 30, "wr": 60.0, "pips": +50.0},
        "by_symbol_24h": [],
    })
    monkeypatch.setattr(sys, "argv", ["v9_edge_alert.py", "--dry-run"])
    rc = v9_edge_alert.main()
    assert rc == 0
    captured = capsys.readouterr()
    assert "EDGE_BAISS_24H" in captured.out or "baissier" in captured.out.lower()
    # State file ne doit PAS exister (dry-run = lecture seule)
    assert not state_file.exists(), (
        f"dry-run ne devrait PAS créer la state file. Trouvé : {state_file}"
    )


def test_format_message_includes_snapshot():
    """Le message Telegram doit inclure le snapshot baissier + haussier."""
    from scripts.v9_edge_alert import _format_message
    alerts = [{
        "pattern": "TEST", "severity": "HAUTE",
        "title": "Test alert", "data": {},
    }]
    edge = {
        "baissier_24h": {"n": 10, "wins": 3, "wr": 30.0, "pips": -200.0},
        "haussier_24h": {"n": 20, "wins": 12, "wr": 60.0, "pips": +50.0},
        "by_symbol_24h": [],
    }
    msg = _format_message(alerts, edge)
    assert "Test alert" in msg
    assert "Baissier" in msg
    assert "Haussier" in msg
    assert "WR=30.0%" in msg or "WR 30.0%" in msg
    assert "-200" in msg


def test_no_alerts_when_edge_healthy(tmp_path: Path, monkeypatch, capsys):
    """Si l'edge est sain, aucune alerte — silencieux."""
    from scripts import v9_edge_alert
    monkeypatch.setattr(v9_edge_alert, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(v9_edge_alert, "_compute_edge", lambda _db: {
        "timestamp": "2026-07-20T14:42:00+00:00",
        "baissier_24h": {"n": 50, "wins": 35, "wr": 70.0, "pips": +200.0},
        "haussier_24h": {"n": 50, "wins": 40, "wr": 80.0, "pips": +300.0},
        "by_symbol_24h": [],
    })
    monkeypatch.setattr(sys, "argv", ["v9_edge_alert.py", "--dry-run"])
    rc = v9_edge_alert.main()
    assert rc == 0
    captured = capsys.readouterr()
    assert "aucun pattern" in captured.out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
