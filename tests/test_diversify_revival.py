"""Tests non-régression — DIVERSIFY 2026-07-16 (Claude Opus).

Réanimation des 6 principes morts (0% hit rate). Chaque cause racine a été
vérifiée sur données réelles (diagnostic 3200+ contextes reconstruits) puis
corrigée. Ces tests verrouillent la correction :

- GRAMMAR_EXHAUSTION : state RUPTURE (pas EARLY_EXTREME/EXTENSION) quand z>=2.
- SIGNAL_OPEN        : window_statut == "ouverte" (pas "exploitable", inexistant).
- GRAMMAR_RESPIRATION: zone_type respiration détecté (vocab compression minuscule).
- GRAMMAR_LOCK       : idem, dépend de zone_type respiration.
- ANTAGONIST_NODE    : dérivation h1/m5 PAR-DEVISE (divergence cross-TF réelle).
- ADAPTIVE_VOL_GATE  : coalition_strength (0-1) vs seuil NORMALISÉ (pas brut 5.38).
"""

from __future__ import annotations

import uuid
from pathlib import Path

from core.v9.behavior_db import init_behavior_db
from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db
from core.v9.exploitability_db import init_exploitability_db
from core.v9.principle_engine import (
    PrincipleEngine,
    _detect_zone_type,
    evaluate_principle,
    load_principles_from_yaml,
)
from core.v9.scene_db import init_scene_db
from core.v9.window_db import init_window_db
from core.v9.zone_db import ZONE_DIAGNOSTICS_COLUMNS, init_zone_db


def _p(pid: str):
    return next(p for p in load_principles_from_yaml() if p.principle_id == pid)


# ── _detect_zone_type : fix vocabulaire compression ───────────────────

def test_detect_zone_type_respiration_lowercase_compression():
    """Vraie valeur DB = "compression" (minuscule), pas "COMPRESSING" (V8).
    Avant le fix, "COMPRESSING" ∉ "COMPRESSION" → respiration jamais détectée."""
    ctx = {"state": "ACCUMULATING", "compression_extension_etat": "compression"}
    assert _detect_zone_type(ctx) == "respiration"


def test_detect_zone_type_no_respiration_when_neutre():
    ctx = {"state": "ACCUMULATING", "compression_extension_etat": "neutre"}
    assert _detect_zone_type(ctx) != "respiration"


def test_detect_zone_type_no_respiration_when_extension():
    ctx = {"state": "ACCUMULATING", "compression_extension_etat": "extension"}
    assert _detect_zone_type(ctx) != "respiration"


# ── evaluate_principle : 6 principes réanimés ─────────────────────────

def test_grammar_exhaustion_triggers_on_rupture():
    """z_current>=2.0 + state RUPTURE (le seul état réel à z extrême)."""
    p = _p("GRAMMAR_EXHAUSTION")
    assert evaluate_principle(p, {"z_current": 2.5, "state": "RUPTURE"})["triggered"] is True


def test_grammar_exhaustion_no_trigger_below_z():
    p = _p("GRAMMAR_EXHAUSTION")
    assert evaluate_principle(p, {"z_current": 1.0, "state": "RUPTURE"})["triggered"] is False


def test_grammar_exhaustion_no_trigger_on_neutral_state():
    p = _p("GRAMMAR_EXHAUSTION")
    assert evaluate_principle(p, {"z_current": 2.5, "state": "NEUTRAL"})["triggered"] is False


def test_grammar_respiration_triggers_on_respiration_zone():
    p = _p("GRAMMAR_RESPIRATION")
    assert evaluate_principle(p, {"zone_type": "respiration"})["triggered"] is True


def test_grammar_respiration_no_trigger_on_indetermine():
    p = _p("GRAMMAR_RESPIRATION")
    assert evaluate_principle(p, {"zone_type": "indetermine"})["triggered"] is False


def test_grammar_lock_triggers_on_compression_and_respiration():
    p = _p("GRAMMAR_LOCK")
    ctx = {"compression_extension_etat": "compression", "zone_type": "respiration"}
    assert evaluate_principle(p, ctx)["triggered"] is True


def test_signal_open_triggers_on_ouverte():
    p = _p("SIGNAL_OPEN")
    ctx = {"window_statut": "ouverte", "confiance_qualification": 75}
    assert evaluate_principle(p, ctx)["triggered"] is True


def test_signal_open_no_trigger_on_legacy_exploitable_value():
    """Non-régression : "exploitable" n'est PAS une valeur de window_statut
    (confusion historique avec exploitability.statut). Ne doit plus déclencher."""
    p = _p("SIGNAL_OPEN")
    ctx = {"window_statut": "exploitable", "confiance_qualification": 75}
    assert evaluate_principle(p, ctx)["triggered"] is False


def test_antagonist_node_triggers_on_per_currency_divergence():
    """h1_dir != m5_dir + 2 états extrêmes (pas NEUTRAL) → antagonisme cross-TF."""
    p = _p("ANTAGONIST_NODE")
    ctx = {
        "h1_state": "HAUSSIERE", "m5_state": "BAISSIERE",
        "h1_dir": "HAUSSIERE", "m5_dir": "BAISSIERE",
    }
    assert evaluate_principle(p, ctx)["triggered"] is True


def test_antagonist_node_no_trigger_when_aligned():
    p = _p("ANTAGONIST_NODE")
    ctx = {
        "h1_state": "HAUSSIERE", "m5_state": "HAUSSIERE",
        "h1_dir": "HAUSSIERE", "m5_dir": "HAUSSIERE",
    }
    assert evaluate_principle(p, ctx)["triggered"] is False


def test_adaptive_vol_gate_triggers_with_normalized_threshold():
    p = _p("ADAPTIVE_VOL_GATE")
    ctx = {
        "vol_regime": "HIGH", "coalition_strength": 0.8,
        "adaptive_coalition_threshold_norm": 0.6,
        "adaptive_antagonism_threshold": 40.0,
        "antagonismes_count": 3, "session_marche": "london",
    }
    assert evaluate_principle(p, ctx)["triggered"] is True


def test_adaptive_vol_gate_no_trigger_below_normalized_threshold():
    p = _p("ADAPTIVE_VOL_GATE")
    ctx = {
        "vol_regime": "HIGH", "coalition_strength": 0.2,
        "adaptive_coalition_threshold_norm": 0.6,
        "adaptive_antagonism_threshold": 40.0,
        "antagonismes_count": 3, "session_marche": "london",
    }
    assert evaluate_principle(p, ctx)["triggered"] is False


# ── Intégration moteur : propagation compression + antagonist par-devise ──

def _make_db(tmp_path: Path) -> Path:
    db = tmp_path / "diversify.db"
    init_db(db)
    init_scene_db(db)
    init_behavior_db(db)
    init_window_db(db)
    init_exploitability_db(db)
    init_zone_db(db)
    return db


def _insert_forces(db: Path, snapshot_id: str, timeframe: str, ts: str,
                   forces: dict, comp: str | None = None) -> None:
    row = {c: None for c in FORCES_COLUMNS}
    row.update({
        "snapshot_id": snapshot_id, "schema_version": "1.0", "timestamp": ts,
        "source": "MT4_SDI", "symbol": "GBPUSD", "timeframe": timeframe,
        "bar_time": 1, "is_closed_bar": True, "mid": 1.0855, "stale": False,
        "created_at": ts, "compression_extension_etat": comp,
    })
    for d, v in forces.items():
        row[f"force_{d.lower()}"] = v
    conn = get_connection(db)
    try:
        conn.execute(
            f"INSERT INTO forces_snapshots ({', '.join(FORCES_COLUMNS)}) "
            f"VALUES ({', '.join(['?'] * len(FORCES_COLUMNS))})",
            [row[c] for c in FORCES_COLUMNS],
        )
        conn.commit()
    finally:
        conn.close()


def _insert_zone(db: Path, ref: str, currency: str, state: str) -> None:
    row = {c: None for c in ZONE_DIAGNOSTICS_COLUMNS}
    row.update({
        "zone_diagnostic_id": f"zd-{uuid.uuid4().hex[:8]}", "schema_version": "1.0",
        "timestamp": "2026-07-05T15:00:00.000Z", "forces_snapshot_ref": ref,
        "symbol": "GBPUSD", "timeframe": "M15", "currency": currency,
        "state": state, "prev_state": state, "z_current": 0.5, "stale": False,
        "created_at": "2026-07-05T15:00:00.100Z",
    })
    conn = get_connection(db)
    try:
        conn.execute(
            f"INSERT INTO zone_diagnostics ({', '.join(ZONE_DIAGNOSTICS_COLUMNS)}) "
            f"VALUES ({', '.join(['?'] * len(ZONE_DIAGNOSTICS_COLUMNS))})",
            [row[c] for c in ZONE_DIAGNOSTICS_COLUMNS],
        )
        conn.commit()
    finally:
        conn.close()


def test_compression_propagated_on_non_h1_m5_timeframe(tmp_path: Path):
    """FIX : compression_extension_etat propagé sur TOUS les TF (ici M15).
    Avant, il n'était posé que dans la branche cross-TF self (H1/M5)."""
    db = _make_db(tmp_path)
    sid = f"v9-m15-{uuid.uuid4().hex[:8]}"
    _insert_forces(db, sid, "M15", "2026-07-05T15:00:00.000Z",
                   {"USD": 55.0, "GBP": 52.0}, comp="compression")
    engine = PrincipleEngine(db_path=db)
    conn = engine._connect()
    try:
        shared = engine._load_shared_context(conn, sid)
    finally:
        conn.close()
    assert shared["context"]["compression_extension_etat"] == "compression"


def test_respiration_zone_type_on_m15_with_accumulating(tmp_path: Path):
    """Chaîne complète : compression propagée (M15) + zone ACCUMULATING pour
    GBP → _detect_zone_type qualifie respiration → GRAMMAR_RESPIRATION déclenche."""
    db = _make_db(tmp_path)
    sid = f"v9-m15-{uuid.uuid4().hex[:8]}"
    _insert_forces(db, sid, "M15", "2026-07-05T15:00:00.000Z",
                   {"USD": 55.0, "GBP": 52.0}, comp="compression")
    _insert_zone(db, sid, "GBP", "ACCUMULATING")
    engine = PrincipleEngine(db_path=db)
    conn = engine._connect()
    try:
        shared = engine._load_shared_context(conn, sid)
        base = shared["context"]
        regime_by = engine._load_per_currency_rows(conn, "regime_snapshots", sid)
        zone_by = engine._load_per_currency_rows(conn, "zone_diagnostics", sid)
        ctx = engine._build_currency_context(base, "GBP", regime_by, zone_by, 52.0)
    finally:
        conn.close()
    assert ctx["zone_type"] == "respiration"
    assert evaluate_principle(_p("GRAMMAR_RESPIRATION"), ctx)["triggered"] is True


def test_antagonist_per_currency_divergence_engine(tmp_path: Path):
    """FIX par-devise : GBP fort sur H1 (>60) mais faible sur M5 (<40) →
    h1_dir/m5_dir divergents POUR GBP, alors que le contexte partagé (devise
    globale) ne divergerait pas. La devise évaluée pilote la dérivation."""
    db = _make_db(tmp_path)
    h1 = f"v9-h1-{uuid.uuid4().hex[:8]}"
    m5 = f"v9-m5-{uuid.uuid4().hex[:8]}"
    # H1 : GBP très fort (80) → h1_dir/state GBP = HAUSSIERE
    _insert_forces(db, h1, "H1", "2026-07-05T14:00:00.000Z",
                   {"USD": 50.0, "GBP": 80.0, "EUR": 50.0})
    # M5 (plus récent) : GBP très faible (15) → m5_dir/state GBP = BAISSIERE
    _insert_forces(db, m5, "M5", "2026-07-05T14:30:00.000Z",
                   {"USD": 50.0, "GBP": 15.0, "EUR": 50.0})
    engine = PrincipleEngine(db_path=db)
    conn = engine._connect()
    try:
        shared = engine._load_shared_context(conn, h1)  # snapshot courant = H1
        base = shared["context"]
        regime_by = engine._load_per_currency_rows(conn, "regime_snapshots", h1)
        zone_by = engine._load_per_currency_rows(conn, "zone_diagnostics", h1)
        ctx = engine._build_currency_context(base, "GBP", regime_by, zone_by, 80.0)
    finally:
        conn.close()
    assert ctx["h1_dir"] == "HAUSSIERE"
    assert ctx["m5_dir"] == "BAISSIERE"
    assert ctx["h1_state"] == "HAUSSIERE"
    assert ctx["m5_state"] == "BAISSIERE"
    assert evaluate_principle(_p("ANTAGONIST_NODE"), ctx)["triggered"] is True
